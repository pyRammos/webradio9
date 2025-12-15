# WebRadio9 Project Context

## Project Overview
WebRadio9 is an event-driven application for scheduling and recording web radio streams, with podcast generation capabilities. The system allows to create and schedule recordings of radio streams, manage the recordings, and create podcasts from these recordings.

## Architecture Decisions
### Principles
-  We do not apply workarounds. If a fix is required, it is part of the product and we can delete recordings, podcasts and even the whole database. This is an important rule.
- During development, we can drop the database. Do not create migration scripts.
- We use python virtual environments
- We separate outputs from inputs. Settings files are under their own folder (called config). Logs go into their own folder too (logs). Recordings also go to their own folder (to be defined in settings)
- All application settings will be part of a settings.cfg file that will have an INI type file structure

### System
- There is only one authenticated user (not a multi user environment). The non authenticated user has access to listen to the recordings and to access the podcast XML/RSS (and download the recordings). The authenticated user has edit abilities thorughout the application.
- There is only one timezone - The application's server timezone. It will be set in the settings file
- When the application first starts, it should check if a recording should be happening (i.e. the current time is after a recording's start time and before its end time)

- There are no GDPR requirements
- The application should allow for logs to be created, and the user specified the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). The log should be available through the web interface too and be filtered by severity and microservice that generated it. Latest entries should be at the top.
- Logs are stored locally only, under a folder called "logs". Delete log entries over 30 days old. Deletion should happen automatically.
- No localisation or multiple languages necessary. Assume UK English localisation and language.
- This is not a critical application. Downtimes are allowed. No need for backup or DR requrements.
- Have a restart button that restarts all microservices and re-loads the settings file. It is limited to the admin only. It should restart the python services.
- There is no limit on concurrent recordings and assume infinite resources.
- Do not expose metrics to any external system
- There are no accessibility requirements
- Assume that the API may be later consumed by native Android or IOS applications.

### Event-Driven Architecture
- Using RabbitMQ as the message broker (running already in Docker)
- Components communicate through events and REST APIs
- Loosely coupled microservices

### Microservices
1. Web Service: Flask application serving the web interface and REST API
2. Station Service: Manages radio stations and validates stream URLs
3. Scheduler Service: Manages recording schedules using APScheduler
4. Recording Service: Handles recording using FFmpeg
5. Storage Service: Manages local and NextCloud storage
6. Metadata Processor: Handles post-processing of recordings
7. Podcast Service: Manages podcasts and generates RSS feeds
8. Notification Service: Sends Pushover notifications
- All microservices are in the same repository and are written in python


### Key Events
- Station events (STATION_CREATED, STREAM_VALIDATED, etc.)
- Recording events (RECORDING_START_REQUESTED, RECORDING_COMPLETED, etc.)
- Storage events (FILE_STORED_LOCAL, etc.)
- Podcast events (PODCAST_EPISODE_ADDED, RSS_FEED_UPDATED, etc.)
- Added RECORDING_PARTIAL event for interrupted recordings that resume
- All messages should use JSON format. Do not enforce versioning.
- Consumers and producers should assume stateless operations. It will be fire and forget

### Recording Status
- COMPLETE - Audio recorded without errors. Finish date and time is in the past
- PARTIAL - There were interruptions in the recording due to external events (app restart, network disconnection, stream issues) but have recovered and at least part of the recording is complete. Finish date and time is in the past
- FAILED - There is no audio file recorded at all and the finish date and time is in the past
- SCHEDULED - Recording has a start date in the future
- RECORDING - Start date is in the past, end date is in the future and audio is being created.

### Storage
- By default recordings are stored locally in a flat folder
- When schedulling recordings, a user can select two additional recording locations. An extra local folder, and a nextcloud instance
- For the two additional recording locations, the files are stored hierarchichally. So, for a recording called NAME, scheduled to start on 30th of January 2025, the recording path would be: [BASE_DIR]/[NAME]/2025/01-Jan/NAME250130-Thu.ext
- A user can select to only keep X recordings. These recordings will be deleted ONLY from the flat folder structure and NEVER from the two additional folders.
- The Web Interface should allow a user to download a recording from the flat folder
- The Web Interface should have a small icon for indicating that a recording has an extra local and/or nextloud storage. Clicking the nextcloud icon should take the user to the nextcloud interface in the folder where the file exists.
- If copying the recording to any of the two additional folder location fails, it should be indicated in the small icon via a colour coding (red=failed, green=success).
- Storage locations (for flat folder, additional local folder and next cloud) are stored in a settingsfile
- Next cloud credentials are stored in the settings file
- If the user selected to only keep X recordings, the storage process should remove them automatically when recording X+1 has happened.
- For next cloud use the python requests library. Assume only one nextcloud account
- Unless a user has selected to only keep X recordings, there is no limit on the number of recordings to keep.
- If a nextcloud upload fails, it should not be retried.

### Radio Stations
- Radio stations are audio streams. The user inputs a name and a URL.
- Once a Radio Station is created, the system will validate it is a valid audio stream and detect its settings (media format, bit rate, etc)
- Use FFProbe to detect the settings

### Recording
- Recording of the audio stream, on time is the most important requirement
- There are two kinds of recordings: 1/One-off (default) and 2/Recurring.
- The user will enter the following minimum info for a recording: 1/Name, 2/Start Time, 3/Duration
- The user can enter the following optional info: 1/Make Recurring, 2/Make Podcast, 3/Save to additional Local Folder, 4/Save to additional NextCloud Folder
- If 'Make Podcast' is selected, the recording will be automatically added as an episode to the selected podcast. Episode metadata (title, description, etc.) is filled in automatically based on the recording and station info at scheduling time.
- Episodes are not manually added or removed from the podcast UI. They are removed only if the admin deletes the recording file via the UI.
- A recurring recording will allow for recordings that happen 1/Daily (same time, every day), 2/On Weekdays only (same time every weekday), 3/On Weekends Only (same time on weekend days), 4/Weekly (same day of the week and same time).
- Concurrent recordings are allowed, but they must have unique names. Assumes that FFMPEG runs as a process. If a recording overlaps with another with the same name, it is ignored. If the name is the same, append a UUID to the filename and reflect it in the web UI.
- The web interface should allow the user to select the recording audio quality (format, bitrate, etc.) but by default it will have the audio stream's settings. Possible options should be MP3, AAC, M4A, MP4.
- FFMPEG will be used to record the audio. If there is audio conversion to happen, it should happen on the fly.
- FFMPEG should be executed with commands to recover from an audio stream interruption, waiting up to 30 seconds between retries, and retrying until the end date/time is scheduled. The system will keep on retrying every 30 seconds, until the end time is reached.
- If a recording is interrupted (PARTIAL) all parts should be merged (appended) in one file using FFMPEG CONCAT.
- Under no conditions should a recording continue past its scheduled recording time.
- When scheduling a recording, the default start date/time is now() + 2 minutes
- The web interface allows the user to listen and download recordings.
- Listening should only be available for formats natively supported by browsers. If the format is not supported, display a message and ask the user to download the file instead.
- The web interface allows the user to delete recordings manually if needed

### Podcasts
- The interface allows the user to create podcast templates with all the info required for an apple podcast specification
- Recordings can be added to any available podcast
- Podcast files are retrieved from the flat local storage. When a file is deleted, it is also removed from the podcast.
- Podcast URLs have a UUID in them to randomise them and make them harder to brute force their links.
- RSS feeds are created on demand and are not cached. Deleted recordings are removed from the RSS feed
- For this initial development phase assume no need for additional feed fields.
- Episodes are created automatically when a recording is scheduled with 'add to podcast'.
- Episodes are removed from the podcast only if the admin deletes the recording file via the UI.
- Episode metadata is filled in automatically at scheduling time and is not edited manually.

### Notifications
- The Pushover notification service's credentials are stored in the settings file
- Pushover notifications will be sent at the end of a recording, indicating the status (COMPLETE, PARTIAL, FAIL), the name, the duration and the file soze of the recording, as well as a link that takes the user to the web interface to listen to the recording.
- Include in the notification any actions that failed (Local storage copy failed, nextcloud failed, etc)
- Do not retry to send the notification
- Assume no other notification integrations are needed

### Database
- Using MySQL/MariaDB (exists in docker container already)
- SQLAlchemy ORM for database interactions
- Assume no need for migrations. If a DB schemma change is needed, then the hole database is dropped and recreated.

### Web Interface
- Flask for backend
- Bootstrap for frontend
- There is only an admin user and the credentials should stored in the settings file. No changes allowed via the web ui.
- The only accessible pages for public access are the podcast and only for read operations (See list, listen and download episodes, or to access the RSS stream)
- Microsoft Outlook web wireframe is aspired.
- The footer of the website will have the local time displayed (HH:mm (24hr format)), refreshed every minute
- Implement basic auth and cookies
- Protect against brute force attempts to log in using exponential back-off
- Admin sessions expire after 1 week regardless if the settings file has been updated
- For the web ui include the following:
  1. Three-Pane Layout
    a. Left Sidebar: Navigation menu (e.g., Stations, Recordings, Schedules, Podcasts, Logs, Settings).
    b. Middle Pane: List view (e.g., list of recordings, schedules, or podcasts with summary info).
    c. Right Pane: Detail view (e.g., selected recording details, player, actions).
  2. Top Navigation Bar
    a. A horizontal bar at the top with the app name/logo, user info, and quick actions (e.g., add new recording, logout).
  3. List with Sorting and Filtering - Ability to sort and filter lists (e.g., recordings by date, status, or station).
  4. Contextual Actions - Right-click or “...” menus for quick actions (e.g., edit, delete, download, add to podcast).
  5. Status Indicators - Colored icons or badges to indicate status (e.g., recording in progress, upload failed, stored in NextCloud).
  6. Responsive Design - Layout adapts to different screen sizes, with collapsible sidebars and panes.
  7. Footer with Local Time - Persistent footer showing the current local time, refreshed every minute.
  8. Consistent Use of Icons - Use of familiar icons for actions (play, pause, download, edit, delete) similar to Outlook’s style.
