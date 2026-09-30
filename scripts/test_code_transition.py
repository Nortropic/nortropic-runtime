"""Automatic code transitions (D043) and their rehearsal's copy, on real git repositories and a synthetic host.

GitHub is a double holding exactly what the real API returns for a published change (pull requests of a commit, check
runs of a head, trees); the binding is the real check_binding of runtime.integration, over sealed request files written
here. The service is never touched: the flow's stop and start are the tested model_choice functions, stood in for by
doubles that record what they were given.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime.integration import check_binding
from scripts import code_rehearsal as rehearsal
from scripts import code_transition as ct
from scripts import model_choice as tool
from scripts.test_model_choice import Host, PATHS

APP = 5110369
TARGET = ct.REPOSITORY


def git(repo, *args, env=None):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


class Chain:
    """A host repository: an active revision, and main advanced by squash merges of reviewed heads."""

    def __init__(self, root):
        self.root = Path(root); self.repo = self.root / 'host'; self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main')
        (self.repo / 'runtime').mkdir(); (self.repo / 'runtime/a.py').write_text('a = 1\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'active')
        self.active = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'remote', 'add', 'origin', str(self.repo))
        self.pulls, self.runs, self.trees, self.requests = {}, {}, {}, {}
        self.number = 70

    def publish(self, path='runtime/a.py', text='a = 2\n', review=None, implementer='impl-1'):
        """One protected publication: a candidate head on its own branch, squash-merged onto main, checks and request."""
        parent = git(self.repo, 'rev-parse', 'main')
        git(self.repo, 'checkout', '-q', '-b', 'cand-%d' % self.number, parent)
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True); (self.repo / path).write_text(text)
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'candidate %d' % self.number)
        head = git(self.repo, 'rev-parse', 'HEAD'); tree = git(self.repo, 'rev-parse', 'HEAD^{tree}')
        git(self.repo, 'checkout', '-q', 'main')
        merge = git(self.repo, 'commit-tree', tree, '-p', parent, '-m', 'squash #%d' % self.number)
        git(self.repo, 'update-ref', 'refs/heads/main', merge); git(self.repo, 'reset', '-q', '--hard', 'main')
        task = {'id': 'runtime-change-%d' % self.number, 'target': TARGET, 'base': parent}
        subject = {'task_id': task['id'], 'candidate': head, 'base': parent, 'implementation_runs': [implementer]}
        review = review or {'verdict': 'approved', 'blocking_findings': [], 'reviewer_run': 'reviewer-1'}
        directory = self.repo / '.runtime/ap11/check-issuer/requests' / task['id']; directory.mkdir(parents=True)
        review_bytes = json.dumps(review).encode()
        (directory / 'review.json').write_bytes(review_bytes)
        (directory / 'request.json').write_text(json.dumps({'schema': 'nortropic-issuer-request/1', 'task': task, 'subject': subject,
                                                            'review': review, 'review_sha256': hashlib.sha256(review_bytes).hexdigest()}))
        binding = check_binding(task, subject, review)
        self.pulls[merge] = [{'number': self.number, 'merged_at': '2026-09-30T10:00:00Z', 'merge_commit_sha': merge,
                              'base': {'ref': 'main'}, 'head': {'sha': head}}]
        self.runs[head] = [{'name': name, 'app': {'id': APP}, 'status': 'completed', 'conclusion': 'success',
                            'completed_at': '2026-09-30T09:59:00Z', 'external_id': binding} for name in ct.CHECKS]
        self.trees[merge] = self.trees[head] = tree
        self.number += 1
        return merge, head


def protection(checks=None, **changes):
    """main's protection as GitHub returns it for the published repository, with changes."""
    value = {'required_status_checks': {'strict': True, 'checks': checks or [
                 {'context': 'runtime/tests', 'app_id': APP}, {'context': 'runtime/review', 'app_id': APP}]},
             'enforce_admins': {'enabled': True}, 'allow_force_pushes': {'enabled': False},
             'allow_deletions': {'enabled': False}, 'required_linear_history': {'enabled': True},
             'required_pull_request_reviews': {'required_approving_review_count': 0}}
    value.update(changes)
    return value


class FakeGitHub:
    def __init__(self, chain, protection=None):
        self.chain = chain
        self.protection = protection or globals()['protection']()

    def main_head(self):
        return git(self.chain.repo, 'rev-parse', 'main')

    def protected_app(self):
        real = ct.GitHub(runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(self.protection), ''))
        return real.protected_app()

    def pulls(self, commit):
        return self.chain.pulls.get(commit, [])

    def check_runs(self, commit):
        return self.chain.runs.get(commit, [])

    def tree(self, commit):
        return self.chain.trees[commit]


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.chain = Chain(self.temp.name); self.github = FakeGitHub(self.chain)

    def verify(self, target=None):
        return ct.verify_chain(self.chain.repo, self.chain.active, target or self.github.main_head(), self.github,
                               check_binding, TARGET)

    def test_two_reviewed_publications_are_proven_one_by_one(self):
        first, head1 = self.chain.publish(); second, head2 = self.chain.publish(text='a = 3\n')
        proven = self.verify()
        self.assertEqual([(p['commit'], p['head'], p['pull_request']) for p in proven], [(first, head1, 70), (second, head2, 71)])
        self.assertEqual(proven[0]['sealed_request'], 'runtime-change-70')

    def refused(self, pattern):
        with self.assertRaisesRegex(ct.Refused, pattern):
            self.verify()

    def test_a_commit_pushed_without_a_pull_request_is_refused(self):
        merge, _ = self.chain.publish(); self.chain.pulls.pop(merge)
        self.refused('exactly one pull request')

    def test_checks_from_another_app_a_failure_or_two_bindings_are_refused(self):
        _, head = self.chain.publish(); good = copy.deepcopy(self.chain.runs[head])
        for change, pattern in ((lambda r: r[0]['app'].update(id=1), 'no runtime/tests check from the protected App'),
                                (lambda r: r[1].update(conclusion='failure'), 'not a completed success'),
                                (lambda r: r[1].update(external_id='nortropic-check/1:other'), 'one binding')):
            self.chain.runs[head] = copy.deepcopy(good); change(self.chain.runs[head])
            self.refused(pattern)

    def test_a_newer_successful_run_counts_over_an_older_failure(self):
        _, head = self.chain.publish()
        self.chain.runs[head].append({**self.chain.runs[head][0], 'conclusion': 'failure', 'completed_at': '2026-09-30T09:00:00Z'})
        self.assertEqual(len(self.verify()), 1)

    def test_checks_without_a_sealed_request_on_this_host_are_refused(self):
        self.chain.publish()
        for directory in (self.chain.repo / '.runtime/ap11/check-issuer/requests').iterdir():
            (directory / 'review.json').write_text('{"verdict": "approved"}')        # no longer the sealed review
        self.refused('no sealed issuer request')

    def test_a_review_that_does_not_approve_or_is_by_the_implementer_is_refused(self):
        self.chain.publish(review={'verdict': 'rejected', 'blocking_findings': ['x'], 'reviewer_run': 'r'})
        self.refused('not an approved separate review')

    def test_the_implementer_reviewing_is_refused(self):
        self.chain.publish(review={'verdict': 'approved', 'blocking_findings': [], 'reviewer_run': 'impl-1'})
        self.refused('not an approved separate review')

    def test_a_merged_tree_other_than_the_reviewed_head_is_refused(self):
        merge, _ = self.chain.publish(); self.chain.trees[merge] = 'f' * 40
        self.refused('merged tree is not the reviewed head tree')

    def test_protection_must_be_exactly_the_two_checks_of_one_app(self):
        self.chain.publish()
        for checks in ([{'context': 'runtime/tests', 'app_id': APP}],
                       [{'context': 'runtime/tests', 'app_id': APP}, {'context': 'runtime/review', 'app_id': 2}]):
            self.github.protection = protection(checks)
            self.refused('exactly the two required checks')

    def test_protection_weaker_than_the_publisher_reads_it_is_refused(self):
        self.chain.publish()
        strict_off = protection(); strict_off['required_status_checks']['strict'] = False
        for weaker in (strict_off, protection(enforce_admins={'enabled': False}), protection(allow_force_pushes={'enabled': True}),
                       protection(allow_deletions={'enabled': True}), protection(required_linear_history={'enabled': False}),
                       protection(required_pull_request_reviews=None)):
            self.github.protection = weaker
            self.refused('weaker than the publisher requires')

    def test_main_that_does_not_descend_from_the_active_revision_is_refused(self):
        self.chain.publish()
        other = git(self.chain.repo, 'commit-tree', git(self.chain.repo, 'rev-parse', 'main^{tree}'), '-m', 'orphan')
        with self.assertRaisesRegex(ct.Refused, 'does not descend'):
            self.verify(other)

    def test_a_request_for_another_repository_is_refused(self):
        self.chain.publish()
        with self.assertRaisesRegex(ct.Refused, 'not an approved separate review'):
            ct.verify_chain(self.chain.repo, self.chain.active, self.github.main_head(), self.github, check_binding,
                            'Nortropic/nortropic-projektkontor')

    def test_owner_files_are_found_in_the_released_selection(self):
        self.chain.publish(path='scripts/model_choice.py', text='x\n'); self.chain.publish(path='docs/notes.md', text='y\n')
        changed = ct.changed_files(self.chain.repo, self.chain.active, self.github.main_head())
        self.assertEqual(changed, ['runtime/scripts/model_choice.py'])
        self.assertTrue(set(changed) & set(ct.OWNER_FILES))

    def test_the_chain_binding_the_check_issuer_and_the_measurement_queue_are_the_owners_too(self):
        for path in ('runtime/integration.py', 'runtime/check_issuer.py', 'runtime/host_publication.py', 'scripts/measurement_queue.py'):
            self.chain.publish(path=path, text='x\n')
        changed = ct.changed_files(self.chain.repo, self.chain.active, self.github.main_head())
        self.assertEqual(set(changed) & set(ct.OWNER_FILES), {'runtime/runtime/integration.py', 'runtime/runtime/check_issuer.py',
                                                              'runtime/runtime/host_publication.py', 'runtime/scripts/measurement_queue.py'})

    def test_the_staged_code_must_be_the_proven_revision_byte_for_byte(self):
        self.chain.publish(path='scripts/tool.py', text='t\n'); self.chain.publish(path='docs/notes.md', text='n\n')
        target = self.github.main_head(); release = self.chain.root / 'release'
        files = {}
        for name in git(self.chain.repo, 'ls-tree', '-r', '--name-only', target).splitlines():
            if ct.released(name):
                data = subprocess.run(['git', '-C', str(self.chain.repo), 'show', '%s:%s' % (target, name)], capture_output=True, check=True).stdout
                (release / 'runtime' / name).parent.mkdir(parents=True, exist_ok=True); (release / 'runtime' / name).write_bytes(data)
                files['runtime/' + name] = hashlib.sha256(data).hexdigest()
        files['office/o.md'] = 'carried'
        ct.code_is_the_revision(self.chain.repo, target, release, files)                   # proven bytes pass
        with self.assertRaisesRegex(ct.Refused, 'other Runtime files'):
            ct.code_is_the_revision(self.chain.repo, self.chain.active, release, files)    # another revision's code
        (release / 'runtime/scripts/tool.py').write_text('planted\n')
        with self.assertRaisesRegex(ct.Refused, 'not byte for byte'):
            ct.code_is_the_revision(self.chain.repo, target, release, files)
        with self.assertRaisesRegex(ct.Refused, 'other Runtime files'):
            ct.code_is_the_revision(self.chain.repo, target, release, {**files, 'runtime/scripts/extra.py': 'x'})


class InvariantTests(unittest.TestCase):
    base = {'runtime_revision': 'a', 'office_revision': 'o', 'instruction_guards': {'g': '1'}, 'watch': {'w': 1},
            'development': {'models': {'claude': 'x'}}, 'files': {'runtime/x.py': '1', 'office/y.py': '2', 'context/c.md': '3'}}

    def test_only_the_runtime_code_revision_and_guards_may_differ(self):
        new = copy.deepcopy(self.base); new.update(runtime_revision='b', instruction_guards={'g': '2'})
        new['files']['runtime/x.py'] = '9'; new['files']['runtime/new.py'] = '8'
        ct.only_code_differs(self.base, new)
        for key, value in (('office_revision', 'p'), ('watch', {'w': 2}), ('development', {'models': {}})):
            changed = copy.deepcopy(new); changed[key] = value
            with self.assertRaisesRegex(ct.Refused, key):
                ct.only_code_differs(self.base, changed)
        changed = copy.deepcopy(new); changed['files']['context/c.md'] = '4'
        with self.assertRaisesRegex(ct.Refused, 'files'):
            ct.only_code_differs(self.base, changed)


class StageTests(unittest.TestCase):
    """Staging on model_choice's synthetic host: code from the target, everything else carried, the choice unchanged."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.host = Host(self.temp.name)
        for patcher in (patch.object(tool.release, 'installed', self.host.installed), patch.object(tool, 'paths', self.host.paths),
                        patch.object(ct, 'probe', lambda host, code, what, *a, **k: {'new-guard': 'v'})):
            patcher.start(); self.addCleanup(patcher.stop)

    def copy_code(self, host, revision, destination):
        destination.mkdir(parents=True)
        files = {'scripts/model_choice.py': Path(tool.__file__).read_bytes(), 'runtime/x.py': b'x = 2\n', 'runtime/new.py': b'n\n'}
        for name, data in files.items():
            (destination / name).parent.mkdir(parents=True, exist_ok=True); (destination / name).write_bytes(data)
            (destination / name).chmod(0o444)
        return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}

    def test_the_new_release_carries_everything_but_the_code(self):
        record_directory, staged = ct.stage(self.host.root, tool, self.copy_code, 'c' * 40, [{'pull_request': 76}],
                                            stamp='20260930T100000Z')
        new = json.loads(Path(staged['config']).read_text()); old = self.host.config
        self.assertEqual(new['runtime_revision'], 'c' * 40); self.assertEqual(new['instruction_guards'], {'new-guard': 'v'})
        for key in ('office_revision', 'development', 'historical_archives', 'host_root', 'database'):
            self.assertEqual(new[key], old[key], key)
        self.assertEqual({k: v for k, v in new['files'].items() if not k.startswith('runtime/')},
                         {k: v for k, v in old['files'].items() if not k.startswith('runtime/')})
        self.assertEqual(staged['changed_runtime_files'], ['runtime/runtime/new.py', 'runtime/runtime/x.py'])
        self.assertEqual(staged['removed_runtime_files'], [])
        self.assertEqual((staged['models_before'], staged['watch_before']), (staged['models_after'], staged['watch_after']))
        self.assertEqual(oct(Path(staged['config']).stat().st_mode & 0o777), '0o400')
        self.assertEqual(ct.latest_for(self.host.root, 'c' * 40, staged['old_config_sha256'])[1], staged)
        with self.assertRaisesRegex(ct.Wait, 'never overwritten'):
            ct.stage(self.host.root, tool, self.copy_code, 'c' * 40, [], stamp='20260930T100000Z')

    def test_a_carried_file_that_changed_in_the_active_release_is_refused(self):
        path = self.host.release / 'context/owner.md'; path.chmod(0o600); path.write_text('changed\n')
        with self.assertRaisesRegex(ct.Refused, 'carried file differs'):
            ct.stage(self.host.root, tool, self.copy_code, 'c' * 40, [])


class FlowTests(unittest.TestCase):
    """automatic(): which state each outcome leaves, and that a decided revision is not tried again."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.chain = Chain(self.temp.name); self.github = FakeGitHub(self.chain)
        (self.chain.repo / '.runtime/ap10').mkdir(parents=True, exist_ok=True)
        self.config = {'runtime_revision': self.chain.active, 'office_revision': 'o' * 40}
        self.calls = []
        mc = type('MC', (), {})()
        mc.active_release = lambda host: ({'config_sha256': 'old-sha', 'directory': str(self.chain.root / 'rel')},
                                          json.dumps(self.config).encode())
        mc.replace, mc.write = tool.replace, tool.write          # the real ones: write refuses an existing file
        mc.outcome = lambda host, directory, staged, text, unexpected=False: self.outcome
        self.mc = mc; self.outcome = 'restored'; self.bases = []
        self.record = self.chain.root / 'record'; self.record.mkdir()
        self.staged = {'sha256': 'new-sha', 'old_config_sha256': 'old-sha', 'old_config': str(self.chain.root / 'rel/config.json'),
                       'config': str(self.chain.root / 'new/config.json'), 'proven': [{'pull_request': 70}]}
        async def calm(mc, margin):
            self.calls.append('quiet')
        for name, value in (('stage', lambda *a, **k: (self.record, self.staged)), ('latest_for', lambda *a: None),
                            ('static_checks', lambda *a: self.calls.append('static')), ('quiet', calm)):
            patcher = patch.object(ct, name, value); patcher.start(); self.addCleanup(patcher.stop)

    def look(self, rehearse_passes=True, preconditions=None, activate=None, rehearse_waits=False):
        async def pre(host, mc, record, staged):
            self.calls.append('preconditions')
            if preconditions:
                preconditions()
        async def act(host, mc, record, staged):
            self.calls.append('activate')
            if activate:
                activate()
        def rehearse(host, old, new, base):
            self.calls.append('rehearse'); self.bases.append(base)
            if rehearse_waits:
                return {'passed': False, 'waiting': True, 'reason': 'work is in progress in the engine copy (t-1)'}
            return {'passed': rehearse_passes, 'reason': None if rehearse_passes else 'the new daemon did not start'}
        with patch.object(ct, 'preconditions', pre), patch.object(ct, 'activate', act):
            return asyncio.run(ct.automatic(self.chain.repo, self.mc, github=self.github, rehearse=rehearse,
                                            copy_code=lambda *a: {}, check_binding=check_binding))

    def test_nothing_new_is_current(self):
        self.assertEqual(self.look()['state'], 'current'); self.assertEqual(self.calls, [])

    def test_unreadable_github_is_a_wait(self):
        self.chain.publish()
        def down():
            raise ct.Wait('GitHub could not be read (offline)')
        self.github.main_head = down
        self.assertEqual(self.look()['state'], 'waiting')

    def test_an_unproven_revision_is_refused_once_and_not_tried_again(self):
        merge, _ = self.chain.publish(); self.chain.pulls.pop(merge)
        first = self.look(); self.assertEqual((first['state'], first['target_revision']), ('refused', merge))
        self.assertEqual(self.look(), first)                              # decided: the status is left as it is

    def test_the_activator_changing_itself_is_the_owners(self):
        self.chain.publish(path='scripts/code_transition.py', text='changed\n')
        value = self.look(); self.assertEqual(value['state'], 'owner_needed'); self.assertIn('code_transition.py', value['reason'])
        self.assertEqual(self.calls, [])

    def test_order_static_quiet_idle_rehearsal_preconditions_activation(self):
        merge, _ = self.chain.publish()
        value = self.look()
        self.assertEqual(self.calls, ['static', 'quiet', 'preconditions', 'rehearse', 'preconditions', 'activate'])
        self.assertEqual((value['state'], value['target_revision'], value['proven'][0]['pull_request']), ('activated', merge, 70))

    def test_a_failed_rehearsal_refuses_before_any_live_check(self):
        self.chain.publish()
        value = self.look(rehearse_passes=False)
        self.assertEqual(value['state'], 'refused'); self.assertIn('did not start', value['reason'])
        self.assertEqual(self.calls, ['static', 'quiet', 'preconditions', 'rehearse'])

    def test_no_rehearsal_starts_while_runtime_works(self):
        self.chain.publish()
        busy = lambda: tool.refuse('work is in progress in the engine: [...]; activate later')
        self.assertEqual(self.look(preconditions=busy)['state'], 'waiting')
        self.assertNotIn('rehearse', self.calls)

    def test_a_passed_rehearsal_is_not_run_again_while_runtime_works(self):
        self.chain.publish()
        seen = []
        def busy_after_the_rehearsal():
            seen.append(1)
            if len(seen) == 2:
                tool.refuse('work is in progress in the engine: [...]; activate later')
        self.assertEqual(self.look(preconditions=busy_after_the_rehearsal)['state'], 'waiting')
        self.assertEqual(self.look()['state'], 'activated')
        self.assertEqual(self.calls.count('rehearse'), 1)

    def test_a_copy_holding_work_is_a_wait_and_the_rehearsal_runs_again_in_a_new_directory(self):
        self.chain.publish()
        value = self.look(rehearse_waits=True)
        self.assertEqual(value['state'], 'waiting'); self.assertIn('engine copy', value['reason'])
        self.assertEqual(self.look()['state'], 'activated')
        self.assertEqual(self.calls.count('rehearse'), 2); self.assertNotEqual(self.bases[0].name, 'rehearsal')
        self.assertTrue(all(b.name.startswith('rehearsal-') for b in self.bases))

    def test_owner_needed_from_the_static_checks(self):
        self.chain.publish()
        def differs(*a):
            raise ct.OwnerNeeded('the AP-10 command differs under the new code')
        with patch.object(ct, 'static_checks', differs):
            self.assertEqual(self.look()['state'], 'owner_needed')

    def test_a_refusal_inside_the_activation_before_any_stop_uses_this_tools_waiting_words(self):
        self.chain.publish()
        self.outcome = 'refused'                   # model_choice's shorter list does not know AP-11
        value = self.look(activate=lambda: tool.refuse('an AP-11 execution is running (ap11-x); a code transition waits'))
        self.assertEqual(value['state'], 'waiting')
        self.outcome = 'waiting'
        value = self.look(activate=lambda: tool.refuse('the staged configuration changed since staging'))
        self.assertEqual(value['state'], 'refused')

    def test_owner_needed_or_refused_raised_by_the_re_check_is_decided_not_retried(self):
        self.chain.publish()
        def owners():
            raise ct.OwnerNeeded('the AP-10 command differs under the new code')
        value = self.look(activate=owners); self.assertEqual(value['state'], 'owner_needed')
        self.assertEqual(self.look(), value)

    def test_a_failed_activation_is_final(self):
        self.chain.publish()
        self.outcome = 'failed'
        value = self.look(activate=lambda: tool.refuse('activation failed and the way back failed; see y'))
        self.assertEqual(value['state'], 'failed')
        self.assertEqual(self.look(), value)

    def test_a_failed_start_that_was_restored_is_final(self):
        self.chain.publish()
        value = self.look(activate=lambda: tool.refuse('activation failed (x); see y'))
        self.assertEqual(value['state'], 'restored')
        self.assertEqual(self.look(), value)

    def test_a_look_cut_off_while_activating_is_interrupted(self):
        self.chain.publish()
        def die():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.look(activate=die)
        value = self.look(); self.assertEqual(value['state'], 'interrupted'); self.assertIn('code-forward', value['reason'])

    def test_the_lock_held_by_another_look_does_nothing(self):
        import fcntl
        self.chain.publish()
        with (self.chain.repo / '.runtime/ap10/automatic-choice.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertIsNone(self.look())


class QuietTests(unittest.TestCase):
    """Heavy work keeps away from the AP-10 watch: model_choice's rule, its refusal turned into a wait."""

    def test_a_refusal_of_the_rule_is_a_wait_and_its_words_are_waiting_words(self):
        mc = type('MC', (), {})()
        async def near(margin):
            tool.refuse('the next AP10 run is less than 20 minutes away (with room for heavy work: %d s); heavy work waits' % margin)
        mc.ap10_quiet = near
        with self.assertRaisesRegex(ct.Wait, 'less than 20 minutes') as caught:
            asyncio.run(ct.quiet(mc, ct.REHEARSAL_MARGIN))
        self.assertTrue(any(f in str(caught.exception) for f in ct.WAITING))


class FetchTests(unittest.TestCase):
    def test_git_runs_without_a_prompt_through_the_owners_gh_login(self):
        seen = {}
        def check_output(argv, **kwargs):
            seen.update(argv=argv, env=kwargs['env']); return b'x\n'
        with patch.object(ct.subprocess, 'check_output', check_output):
            ct.git('/h', 'fetch', '--quiet', 'origin', 'main')
        env = seen['env']
        self.assertEqual((env['GIT_TERMINAL_PROMPT'], env['GIT_CONFIG_VALUE_0'], env['GIT_CONFIG_VALUE_1']), ('0', '', '!gh auth git-credential'))
        self.assertFalse({'GH_TOKEN', 'GITHUB_TOKEN'} & set(env))


class GitHubTests(unittest.TestCase):
    def test_every_question_is_a_read_through_gh_api(self):
        seen = []
        def runner(argv, **kwargs):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps({'commit': {'sha': 'x', 'tree': {'sha': 't'}}, 'check_runs': []}), '')
        hub = ct.GitHub(runner=runner)
        hub.main_head(); hub.tree('c'); hub.check_runs('h'); hub.pulls('c')
        self.assertTrue(all(a[:2] == ['gh', 'api'] and '-X' not in a and '--method' not in a for a in seen))

    def test_check_runs_are_the_latest_of_each_and_every_page_is_read(self):
        pages = {1: {'total_count': 3, 'check_runs': [{'name': 'a'}, {'name': 'b'}]}, 2: {'total_count': 3, 'check_runs': [{'name': 'c'}]}}
        seen = []
        def runner(argv, **kwargs):
            seen.append(argv[-1]); page = int(argv[-1].rsplit('page=', 1)[1])
            return subprocess.CompletedProcess(argv, 0, json.dumps(pages[page]), '')
        self.assertEqual([r['name'] for r in ct.GitHub(runner=runner).check_runs('h')], ['a', 'b', 'c'])
        self.assertTrue(all('filter=latest' in s for s in seen)); self.assertEqual(len(seen), 2)

    def test_a_failure_is_a_wait(self):
        hub = ct.GitHub(runner=lambda argv, **k: subprocess.CompletedProcess(argv, 1, '', 'HTTP 502'))
        with self.assertRaisesRegex(ct.Wait, 'HTTP 502'):
            hub.main_head()


class RehearsalCopyTests(unittest.TestCase):
    def test_only_port_literals_in_code_shift_and_markdown_is_left(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'release'; (source / 'runtime').mkdir(parents=True)
            (source / 'runtime/a.py').write_text("PORTS = (7339, 7340, 7341)\nX = 173390\nY = 'v7339'\n")
            (source / 'context.md').write_text('7339\n')
            changes = rehearsal.shift(source, Path(temp) / 'copy')
            self.assertEqual(changes, ['runtime/a.py'])
            self.assertEqual((Path(temp) / 'copy/runtime/a.py').read_text(), "PORTS = (27339, 27340, 27341)\nX = 173390\nY = 'v7339'\n")
            self.assertEqual((Path(temp) / 'copy/context.md').read_text(), '7339\n')

    def test_a_live_port_literal_outside_python_code_refuses(self):
        for name in ('runtime/config/engine.json', 'runtime/tools/start.sh'):
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / 'release'; (source / name).parent.mkdir(parents=True)
                (source / name).write_text('{"port": 7340}\n')
                with self.assertRaisesRegex(ValueError, 'outside Python code'):
                    rehearsal.shift(source, Path(temp) / 'copy')

    def test_the_profile_is_deny_rules_only_for_the_network_writes_and_programs(self):
        base = '/h/Nortropic Runtime/.runtime/ap10/code-transitions/x/rehearsal-1'
        lines = rehearsal.profile(base).splitlines()
        self.assertEqual([l for l in lines if l.startswith('(allow')], ['(allow default)', '(allow process-exec (literal "/bin/ps") (with no-sandbox))'])
        self.assertIn('(deny network-outbound (require-not (remote ip "localhost:*")))', lines)
        for port in (7339, 7340, 7341):
            self.assertIn('(deny network-bind (local ip "*:%d"))' % port, lines)
        self.assertIn('(deny file-write* (require-not (require-any (subpath "%s") (literal "/dev/null") (literal "/dev/tty") '
                      '(literal "/dev/dtracehelper"))))' % base, lines)
        self.assertIn('(deny process-exec (literal "/bin/launchctl") (literal "/usr/bin/sudo") (literal "/usr/bin/su"))', lines)

    def test_a_connection_to_a_port_no_copy_process_listens_on_is_found(self):
        listings = {True: 'p10\nf5\nn127.0.0.1:27339\np11\nf7\nn127.0.0.1:52001\n',
                    False: ('p10\nf5\nn127.0.0.1:27339\nf6\nn127.0.0.1:27339->127.0.0.1:60001\n'
                            'p12\nf3\nn127.0.0.1:60001->127.0.0.1:27339\nf4\nn127.0.0.1:60002->127.0.0.1:7339\n'
                            'f8\nn127.0.0.1:60003->127.0.0.1:52001\n')}
        def run(argv, **kwargs):
            self.assertEqual(argv[:4], ['/usr/sbin/lsof', '-nP', '-a', '-p']); self.assertEqual(argv[4], '10,11,12')
            return subprocess.CompletedProcess(argv, 0, listings['-sTCP:LISTEN' in argv], '')
        with patch.object(rehearsal.subprocess, 'run', run):
            self.assertEqual(rehearsal.own_connections([12, 10, 11]), {'seen': 4, 'outside': ['12 127.0.0.1:60002->127.0.0.1:7339']})

    def test_the_children_get_a_home_and_temporary_directory_of_their_own(self):
        env = rehearsal.environment(Path('/b/root'), 'd')
        self.assertEqual((env['HOME'], env['TMPDIR'], env['NR_HOST_ROOT'], env['NR_CONFIG_SHA256']), ('/b/home', '/b/tmp/', '/b/root', 'd'))
        self.assertNotIn(str(Path.home()), json.dumps(env))

    def test_a_copy_with_pending_work_is_busy(self):
        rows = [{'id': 'idle'}, {'id': 'act', 'pending_activities': 1}, {'id': 'task', 'pending_workflow_task': True}]
        self.assertEqual(rehearsal.copy_busy(rows), ['act', 'task'])


class OwnerForwardTests(unittest.TestCase):
    """model_choice.py code-forward: the owner's continuation checks what do_forward checks, by the NEW code."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        host = Path(self.temp.name); self.host = host
        record = host / '.runtime/ap10/code-transitions/20260930T100000Z'; activation = record / 'activation-20260930T100100Z'
        activation.mkdir(parents=True)
        config = host / 'new/config.json'; config.parent.mkdir(); config.write_text('{"files": {}}')
        self.staged = {'tool_sha256': hashlib.sha256(Path(ct.__file__).read_bytes()).hexdigest(), 'config': str(config),
                       'sha256': hashlib.sha256(config.read_bytes()).hexdigest(), 'runtime_revision': 'r' * 40}
        (record / 'staged.json').write_text(json.dumps(self.staged))
        (activation / 'state.json').write_text(json.dumps({'staged': self.staged, 'stop_completed': True, 'old_service': {}}))
        self.calls = []
        mc = type('MC', (), {})()
        mc.latest_activation = lambda directory: activation
        mc.alive = lambda service: {}
        mc.read_json = lambda path, what: {}
        mc.paths = lambda host: {'service': host / 'service.json'}
        mc.verify_files = lambda *a: self.calls.append('verify')
        mc.replace = lambda path, data: Path(path).write_bytes(data)
        mc.refuse = tool.refuse
        async def forward(host, state, directory, progress):
            self.calls.append('forward')
        mc.forward = forward
        self.mc = mc

    def test_the_new_codes_offline_checks_come_before_forward(self):
        with patch.object(ct, 'probe', lambda *a, **k: self.calls.append(a[2])), \
                patch.object(ct, 'code_is_the_revision', lambda *a: self.calls.append('git')):
            asyncio.run(ct.owner_forward(self.host, self.mc))
        self.assertEqual(self.calls, ['verify', 'git', 'offline', 'forward'])

    def test_staged_code_that_is_not_the_proven_revision_is_not_forwarded(self):
        def planted(*a):
            raise ct.Refused('the staged Runtime code is not byte for byte the proven revision')
        with patch.object(ct, 'code_is_the_revision', planted), self.assertRaisesRegex(SystemExit, 'not byte for byte'):
            asyncio.run(ct.owner_forward(self.host, self.mc))
        self.assertNotIn('forward', self.calls)

    def test_a_failing_offline_check_or_another_tool_refuses(self):
        def fails(*a, **k):
            raise RuntimeError('an unfinished writer is recorded')
        with patch.object(ct, 'probe', fails), patch.object(ct, 'code_is_the_revision', lambda *a: None), \
                self.assertRaisesRegex(SystemExit, 'offline daemon start requirements'):
            asyncio.run(ct.owner_forward(self.host, self.mc))
        with patch.object(ct, 'sha_bytes', lambda data: 'other'), self.assertRaisesRegex(SystemExit, 'not the one that staged'):
            asyncio.run(ct.owner_forward(self.host, self.mc))
        self.assertNotIn('forward', self.calls)


if __name__ == '__main__':
    unittest.main()
