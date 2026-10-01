import hashlib
import unittest
from runtime import decision_guard as d

POLICY={'literals':[]}
OLD=b'# Decisions\n\n## D001\nRetain accepted words.\n\n## D002\nSecond decision.\n'


class Decisions(unittest.TestCase):
    def test_append_wrap_and_insertion_preserve_words(self):
        for new in (OLD+b'\n## D003\nAddition.\n',OLD.replace(b'Retain accepted',b'Retain\n accepted'),OLD.replace(b'accepted',b'new accepted')):
            self.assertTrue(d.inspect(OLD,new,POLICY)['passed'])
    def test_deleted_section_and_removed_words_refuse(self):
        for new in (OLD.split(b'## D002')[0],OLD.replace(b'accepted ',b''),OLD.replace(b'accepted words',b'words accepted')):
            with self.assertRaises(d.ContentRefused):d.inspect(OLD,new,POLICY)
    def test_new_superseded_and_explicit_new_correction_only(self):
        self.assertTrue(d.inspect(OLD,OLD.replace(b'accepted words.',b'SUPERSEDED'),POLICY)['passed'])
        new=OLD.replace(b'accepted ',b'')+b'\n## D003\nCorrection of: D001\nExplains the correction.\n'
        self.assertEqual(d.inspect(OLD,new,POLICY)['exceptions'],[{'id':'D001','basis':'named-correction'}])
        for bad in (new.replace(b'Correction of: D001',b'D001 is merely mentioned'),new.replace(b'Correction of: D001',b'Correction of: D002')):
            with self.assertRaises(d.ContentRefused):d.inspect(OLD,bad,POLICY)
        prior=OLD.replace(b'accepted words.',b'SUPERSEDED accepted words.')
        with self.assertRaises(d.ContentRefused):d.inspect(prior,prior.replace(b'accepted ',b''),POLICY)
    def test_exact_redaction_is_not_permission_to_remove_other_text(self):
        home='/'+'Users'+'/synthetic/'
        old=('## D001\nKeep '+home+' other words.\n').encode()
        new=d.redacted(old.decode(),[]).encode()
        self.assertTrue(d.inspect(old,new,POLICY)['passed'])
        for bad in (new.replace(b'other ',b''),new.replace(hashlib.sha256(home.encode()).hexdigest().encode(),b'0'*64)):
            with self.assertRaises(d.ContentRefused):d.inspect(old,bad,POLICY)
    def test_duplicate_identity_fenced_heading_and_preamble(self):
        with self.assertRaises(d.ContentRefused):d.inspect(OLD,OLD+b'## D001\nDuplicate\n',POLICY)
        self.assertEqual(len(d.sections(b'## D001\n```md\n## D002\n```\n')),2)
        with self.assertRaises(d.ContentRefused):d.inspect(OLD,OLD.replace(b'# Decisions',b'# Changed'),POLICY)
