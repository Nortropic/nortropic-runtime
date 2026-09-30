"""Host-owned review instructions; candidate text cannot lower acceptance."""
SECRET_INSTRUCTION = (
    'Report suspected real secrets or private data in the candidate as blocking findings, '
    'without reproducing their values. This includes keys, tokens, home-directory paths, '
    'raw model-session logs and personal data. Documented placeholders and synthetic test '
    'fixtures are not secrets. Private review evidence is not itself candidate publication content. '
)
LIMITS_INSTRUCTION = (
    'Never claim an unrun check passed. Never lower the accepted requirements. '
    'List checks you did not perform or could not run in limitations; use an empty list '
    'only when there are none. A stated limitation does not waive any acceptance requirement. '
)
