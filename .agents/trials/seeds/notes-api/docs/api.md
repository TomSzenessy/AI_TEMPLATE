# Notes API

| Method | Path | Body | Result |
|---|---|---|---|
| GET | /notes | | all notes, newest first |
| POST | /notes | `{"title": "...", "body": "..."}` | 201 with the new id; 400 without a title |
| GET | /notes/{id} | | the note, or 404 |
| DELETE | /notes/{id} | | 204, or 404 |

Clients in production: the team's Slack bot posts to `POST /notes`, so the
existing request and response shapes must stay compatible.
