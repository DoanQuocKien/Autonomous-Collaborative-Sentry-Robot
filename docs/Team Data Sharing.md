# Sharing datasets inside the team

Raw datasets and recordings stay in ignored `data/`. Encrypted transfer archives
stay in ignored `team_data/*.zip` and are shared privately, with the password
provided separately. They are excluded from the Week 7 submission tree.

```bash
# Set TEAM_DATA_PASSWORD privately, or let the command prompt for it.
python -m tools.team_data pack data/D2/1028 team_data/D2_1028.zip
python -m tools.team_data unpack team_data/D2_1028.zip data/D2/1028
```

The tool reads `--password`, `TEAM_DATA_PASSWORD`, then an interactive prompt.
Do not put the password in source, issue comments or documentation. Re-encrypt
old archives when changing the password. Do not add archives or raw data to Git.

Historical note: the 28/10 protocol committed an encrypted D2 archive with a
password in source; DQK's 13/11 draft records the team's acceptance of that risk.
The Week 7 package removes these files from its current tree and code defaults;
existing commits still contain them. This change neither rewrites the team's
history nor claims that it is safe to republish that history. Use the ZIP from
`python -m tools.build_midterm_package --ref <commit> --out <new-file.zip>`
for the current-tree submission fallback without `.git`.
