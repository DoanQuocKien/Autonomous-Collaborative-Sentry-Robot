# Sharing local datasets inside the team (protocol of 2026-10-28)

Datasets with faces or recordings (D1 doors, D2 entries, D5 unmasked, handshake frames) stay in `data/` (git-ignored) and are never committed unzipped. To hand one to a teammate, pack it as a **password-protected AES zip, commit the zip in `team_data/` in a PR**, and the teammate unpacks it into their own `data/`. One protocol, no Drive links to chase, and the data arrives with the code it belongs to.

**Sender**
```
python -m tools.team_data pack data/D2/1028 team_data/D2_1028.zip     # put a README.txt in the folder first: what is inside, who recorded it, the limits
git add team_data/D2_1028.zip; commit; PR (one review)
```
**Receiver** (after the PR is merged and `git pull`)
```
python -m tools.team_data unpack team_data/D2_1028.zip data/D2/1028
```
`pip install pyzipper` once (it is in `requirements-base.txt`). 7-Zip also opens the zip; Windows Explorer may not (AES).

**Password: `12345678`** (the team standard, `tools/team_data.py`). It keeps the files unreadable for anyone who only finds the zip. It is **not** a secret inside the team and not strong protection, because it sits in this repository.

**What this does not do**
- A committed zip stays in the git history **forever**, also after it is deleted from the branch. The repository is private; after grading it is deleted or archived (same rule as the D5 exception in `Implementation Plan.md` section 4.2).
- Frames that show bystanders (the D2 cafe set) are shared inside the team only, never in the report or video unmasked (`tools/mask_faces.py` first).
- GitHub refuses single files over 100 MB: bigger sets go through the team Drive, with the same password on the zip.
- Never commit the unzipped folder, and never run `git add data/`.
