# Classroom studying time Tracker

The class list, praise, and warnings stay in `website/`. The phone app in `android/` is only a window that opens the page on Aliyun.

## On this Mac

From `website/`, run:

```bash
python3 mt_server.py
```

Then open `http://127.0.0.1:8765/`. **Save to Aliyun** copies the session file, the student records, and the praise notes to the server. The save token and the certificate password stay in this folder and are not stored in git.

## On the phone

Install the certificate, then the app. The app asks for that certificate and then for the save token. After that, the class list comes from Aliyun.

## Weekly summary

**Weekly summary** uses the sessions dated in the last 7 days.

- **Positive report** is everyone tied for the highest praise count.
- **Quasi-positive** is everyone else who was praised. They receive house points for this week only.
- **Need a warning** is everyone who was warned.

There is no extra weight the following week.

## Manage students

**Manage students** adds a name, changes a name or Chinese name, or deletes a name. The search box filters that list the same way it filters the student cards. Changing a name keeps that student's earlier praise and warnings. The list is kept in this browser. The next save sends it to Aliyun with the sessions.

**Reset to Baseline** asks twice, then restores the original sessions. It does not change the class list.

## What git does not keep

Session history, student records, praise notes, the save token, and the certificate password stay on this Mac. The tracker page still contains the original class list so the page can open before a saved list exists.
