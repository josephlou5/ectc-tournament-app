# Developer Guide

This guide is to be the main source of information for how the codebase of this
system is structured, how it works, and what it does.

## Table of Contents

- [General](#general)
  - [Pipenv](#pipenv)
    - [Virtual Environment](#virtual-environment)
    - [Installing Dependencies](#installing-dependencies)
    - [Adding New Packages](#adding-new-packages)
  - [Development Helpers](#development-helpers)
- [Deployment](#deployment)
  - [Building and Starting](#building-and-starting)
  - [Environment Variables](#environment-variables)
- [Codebase](#codebase)
  - [Flask app](#flask-app)
    - [Config](#config)
  - [Modularized Routes](#modularized-routes)
  - [Database](#database)
    - [Migrations](#migrations)
  - [Views](#views)
    - [`fetch_matches_info()`](#notifications-fetch_matches_info)
    - [`send_match_notification()`](#notifications-send_match_notification)
    - [`send_blast_notification()`](#notifications-send_blast_notification)
    - [`fetch_roster()`](#admin-fetch_roster)
  - [Templates](#templates)
  - [Development Tips](#development-tips)
    - [Log in as anyone](#log-in-as-anyone)
    - [Disable Mailchimp functions](#disable-mailchimp-functions)

## General

I used VSCode for development. The relevant extensions used in this project are:

- Python: language support
- isort: sorting Python imports
- Prettier: code formatter for Markdown, HTML, and JavaScript
- Jinja: language support
- Better Jinja: syntax highlighting for Jinja2

The Python version used was 3.11.1. For Python package management, I used
[`pipenv`][] (see the [`Pipfile`][]). The dev packages used were [`black`][]
(for formatting), [`isort`][] (for import sorting), and [`pylint`][] (for
linting). For dev package config, I used a [`pyproject.toml`][] file, which
currently only defines the line lengths for `black` and `isort`. This was done
so that the configs would be in a single file rather than multiple `.cfg` files
or something else not centralized.

### Pipenv

#### Virtual Environment

To create or enter the virtual environment for the project, run:

```bash
$ pipenv shell
```

To exit the virtual environment, run:

```bash
$ exit
```

I personally like my virtual environments to be in the same directory as my
project, so I set `PIPENV_VENV_IN_PROJECT=1` in my `~/bash_profile`, which will
create a `.venv/` subdirectory when you create the virtual environment for the
first time (or when installing packages for the first time). Otherwise, it will
create the virtual environments in a directory somewhere else on your machine,
which you will be able to see the path for when you run `pipenv shell`.

#### Installing Dependencies

To install all the dependencies, run:

```bash
$ pipenv install
```

To also include the development packages, run:

```bash
$ pipenv install -d
```

#### Adding New Packages

If the project has a new package dependency, run:

```bash
$ pipenv install <package>
```

For a new development package, run:

```bash
$ pipenv install -d <package>
```

Note that `pipenv` does not save the installed version in the `Pipfile` itself
(see [issue #5531](https://github.com/pypa/pipenv/issues/5531)). The contents of
this `Pipfile` were manually set whenever a package was installed (with the
`"~=X.Y.Z"` syntax to lock the major version). Be wary of this so that new
versions of the dependencies don't break any code.

### Development Helpers

To start a development server, run the script [`src/runserver.py`], which will
start a local server at https://localhost:5000.

Note that we are using HTTPS here instead of HTTP. There is a
[`before_request`](src/app.py#L64) hook in `app.py` that forces HTTPS. In a
production server, the deployment service will likely be secure anyway, but when
testing locally, you will need `cert.pem` and `key.pem` files in the root
directory (ignored in `.gitignore`). I used [this tutorial][cert tutorial] to
generate the certificate files.

For authentication through Google to work, you need a client id and secret from
a registered Google application. I used
[this tutorial][google authentication tutorial] and example code from my
advisor, Professor Dondero. See [`src/views/auth.py`][] for all the
authentication callbacks and handling.

The client id and secret from Google will need to be set in environment
variables called `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, respectively.
Therefore, it would be easiest to create a script `runserver.sh` (ignored in
`.gitignore`) in the root directory with the contents:

```bash
GOOGLE_CLIENT_ID="your-client-id" \
GOOGLE_CLIENT_SECRET="your-client-secret" \
python src/runserver.py
```

This way, you can simply run `bash runserver.sh` inside a virtual environment
(see the [Virtual Environment](#virtual-environment) section) to easily start a
development server.

## Deployment

I used [Render][] for deployment, but you are free to use whatever you want.

### Building and Starting

There are two scripts, [`build.sh`][] and [`start.sh`][], for use in deployment.

`build.sh` contains the commands to set up the project in a deployment
environment. It will install `pipenv` and all the required packages through the
`pipenv` CLI. It will then run the database migrations in case the database
schema was changed since the last deployment.

`start.sh` contains the commands to start the deployed server. This uses
[`gunicorn`][] to change into the `src/` directory and start the Flask app in
`app.py`.

In the deployment service, you should be able to set a build command and a start
command. You can now easily do:

- Build command: `./build.sh`
- Start command: `./start.sh`

### Environment Variables

These are the environment variables you will need to have set for deployment:

- `PYTHON_VERSION`: Set this to `3.11.1`.
- `PROD_SECRET_KEY`: Set this to some random value for secure AJAX requests.
  Here is some basic code to generate one:

  ```python
  import random
  import string
  ALPHABET = string.ascii_letters + string.digits
  length = 50
  secret_Key = "".join(random.choice(ALPHABET) for _ in range(length))
  ```

- `SQLALCHEMY_DATABASE_URI`: The uri to the production database.
- `GOOGLE_CLIENT_ID`: The client id for authentication through Google.
- `GOOGLE_CLIENT_SECRET`: The client secret for authentication through Google.

## Codebase

All the source code is located within the [`src/`][] directory.

### Flask app

The system uses a Flask server, located in [`src/app.py`][]. This file also
contains other setup functions and error page handling.

#### Config

The [`src/config.py`][] file defines configuration objects that get passed to
the Flask app when it starts. We need the `SECRET_KEY` attribute for secure AJAX
requests (taken from the environment variable `"PROD_SECRET_KEY"`) and a
`SQLALCHEMY_DATABASE_URI` attribute to connect to our database (taken from the
environment variable `"SQLALCHEMY_DATABASE_URI"`) (see the [Database](#database)
section).

During development, instead of taking these values from the environment
(although that is also completely valid), I used a file called `src/keys.py`
(ignored by `.gitignore`) that defined two variables, `DEV_SECRET_KEY` and
`DEV_POSTGRES_PASSWORD`. I then imported these values into `config.py` and used
them if debug was on. Since I was also using a local PostgreSQL database for
development, I was able to hardcode the connection values such as the username
and database name. However, you might want to change these if you're using a
different development database.

### Modularized Routes

Normally in a Flask app, you would use the `@app.route()` decorator to define a
function as a route in the app, such as the index page. However, doing so
requires access to the `app` variable defined in `app.py`. To be able to
modularize all the views between different files, you would either have to
import the `app` into all the view files or import all the views into `app.py`.
Since importing Python modules between subdirectories can get a bit tricky, I
decided to go with the latter option and simply import a `views` subpackage into
`app.py`, then call a custom `register_all()` function with the `app` itself
passed to it.

In [`src/utils/server.py`][], you can find the [`AppRoutes`][] class, which acts
as a mock Flask "app" that has the same `@app.route()` decorator. In this way,
a route can be defined in any file like so:

```python
app = AppRoutes()

@app.route("/", methods=["GET"])
def index():
    return "Hello, world!"
```

In [`register_all()`][], all the `AppRoute` instances are imported from the
[`src/views/`][] subpackage, and all the mock routes are registered with the
actual Flask app. This is done with the `app.add_url_rule()` method to manually
add a route without the decorator.

By doing all these steps, I was able to split all the routes into different
modules organized by purpose or permission. This made defining routes much
easier, and with the standardized way of using the decorator, routes could be
easily moved between files without any other changes.

Note: Another option would have been to look into [Flask blueprints][]. My
method seemed simpler to me, but a future maintainer might want to look into
that for a Flask application that uses the intended features.

See the [Views](#views) section for a description of each of the files in this
directory.

### Database

All the code relating to the database is located in the [`src/db/`][] submodule.

The system uses the [Flask-SQLAlchemy][] extension to connect the Flask app with
a PostgreSQL database. All the models are in [`src/db/models.py`][], and the
rest of the files are helper methods relating to each model.

As mentioned in the [Config](#config) section, you must provide the information
for the development database you are using in [`src/config.py`][dev database].

The `db` instance in `models.py` is the actual connection to the database, and
is used throughout the submodule to perform database actions.

#### Migrations

The databases uses [Flask-Migrate][] to create migrations and update the
database. After a change is made to the models (such as editing columns or
adding or deleting a table), you must migrate the changes so that the actual
database you are using (the development database) is updated appropriately. I
will describe the general steps below, but see the official documentation for
more details.

In all of these sample commands, I prefix the command with `FLASK_DEBUG=True`.
This is so that Flask-Migrate uses the development database as set in the app
configuration. There might be a better way to do this, but I haven't really
looked into it.

Also note that these commands must be run in the virtual environment so that
Flask-Migrate can be accessed.

1. First, you need to create a migration, which specifies what to do when a
   database is upgrading to this version (via the `upgrade()` function) and what
   to do when a database is downgrading from this version (via the `downgrade()`
   function). This allows the database to easily accept or revert any changes
   made.

   ```bash
   # Migrate all changes
   $ FLASK_DEBUG=True flask db migrate
   ```

   This will create a migration file in [`migrations/versions/`][]. It will be
   named with a random hash. You can also provide a message for the migration
   with the `-m` option, which will be appended to the filename. I usually
   generate the migrations without a message, then edit the docstring manually
   in the file (in case I change the message in the future, I don't want to have
   to also rename the file and whatnot).

   You can always edit these migration files as needed before updating the
   database. However, be sure that the `downgrade()` function always undoes
   everything in the `upgrade()` function so that there are no conflicts in the
   database. In addition, be careful of errors such as trying to add a
   non-nullable column to a table that already has rows in it (you will need to
   add the column, give a default or initial value to each row, then add the
   non-nullable constraint). I have some examples of edited migration files for
   my specific purposes in [`migrations/versions/`][].

2. Next, you need to actually update the database. The database will keep track
   of the current version it is at, so you can update with multiple migrations
   in the queue, so to speak. Each one will be updated in order by calling its
   `upgrade()` function.

   ```bash
   # Update with all new migrations
   $ FLASK_DEBUG=True flask db upgrade
   ```

3. If you ever need to revert any database changes, you can run:

   ```bash
   # Downgrade by one migration
   $ FLASK_DEBUG=True flask db downgrade
   ```

   This will revert a single migration by calling its `downgrade()` function.

As mentioned in [Building and Starting](#building-and-starting), the `build.sh`
script migrates all the changes into the production database. This is done by
simply running `flask db upgrade`, which will update the database with all the
migrations since the last deployment (or do nothing if the database is
up-to-date).

### Views

The [`src/views/`][] directory contains all the routes for the system. Each file
has a pretty straightforward purpose from its name or docstring. Most of the
routes are also pretty straightforward, communicating with or changing the
database toward the desired result. A lot of the `GET` routes either return a
rendered template (see the [Templates](#templates) section) or a JSON object (a
Python dictionary); the latter are used for AJAX requests.

In this section, I will describe some of the more complicated views and what
they do. The other ones should be straightforward.

#### Notifications: `fetch_matches_info()`

The [`fetch_matches_info()`][] view
(`/notifications/matches_info?matches=matchesQuery`) will fetch the info for
the given matches query arg. It also accepts an optional `previous=matchesQuery`
arg, and all matches in the combined queries will be fetched and returned.

The matches query is a query string that is typed in to the "Add Matches" input
on the Notifications page. It is parsed by [`parse_matches_query()`][], which
returns all the found match numbers according to the match query rules. The
[`fetch_match_teams()`][] function is then used to fetch the information of all
the specified matches from the "Communications" sheet.

This function will first look for the header row, which is defined by the first
row in the sheet that has all the expected unique header values (case
insensitive and in any order). The values in the rest of the rows will then be
assumed to all have values in each column corresponding to its header in the
header row. All the rows with the requested match numbers will be returned (only
the first row will be returned if multiple rows have the same match number), and
all the match statuses will also be saved in the database for displaying on the
TMS Matches Status page (only the first status seen for each match number will
be saved if multiple rows have the same match number). This sheet is assumed to
only have the names of the blue and red teams for each match number.

After the match infos are fetched, they will be processed again to detect any
warnings, such as a match having a single team as both blue and red or a team
being in multiple matches. All the actual team information (such as members)
will then be fetched from the database and combined into the match info. If a
team is invalid (such as not being found in the database), appropriate errors
are also handled here. If there is at least one match fetched, the matches table
will be rendered with the [`matches_info_rows.jinja`][] template, and the HTML
will be returned as a string in a JSON object (which the Notification page's
AJAX handler will then put into the page).

The rendered table will include compact match info for each match in the form of
an attribute on its row. This info string will be used to send match
notifications, so triggering a send doesn't actually fetch any new information
from the TMS.

#### Notifications: `send_match_notification()`

The [`send_match_notification()`][] view (`/notifications/send/matches`) will
send a notification with the given args (not listed in this example route),
including `templateId`, `subject`, `matches` (list of match infos),
`sendToCoaches`, `sendToSpectators`, and `sendToSubscribers`.

The [`validate_subject()`][] function is used to validate a subject (with the
valid characters) and possible placeholders for non-blast notifications.

All the valid matches are first filtered out (valid being defined as the info
having all the expected keys). If there are no errors, the notifications will be
sent. For each match, the recipient emails are compiled (according to the team
info and any additional recipients). A subject is generated for each team (using
appropriate placeholder values), and if they are the same, all the email
addresses are combined into a single notification. Finally, the Mailchimp helper
functions are called to actually send the notification emails.

The information for all the sent emails will be saved in the database to be
displayed on the Sent Emails page.

Note that the Mailchimp API calls simply _trigger_ the email sends. There is a
way for us to add a webhook to be able to tell when the emails have actually
been sent (or if there was an error along the way), which is not being done now
but could be implemented in the future.

#### Notifications: `send_blast_notification()`

The [`send_blast_notification()`][] view
(`/notifications/send/blast?templateId=template&subject=subject`) will send a
blast notification to the given tournament tag, the entire selected Mailchimp
audience, or a specific division. It will validate the subject (not allowing
placeholders), fetch the relevant recipient emails, and then send a single blast
notification.

The information for all the sent blast emails will be saved in the database to
be displayed on the Sent Emails page.

#### Admin: `fetch_roster()`

The [`fetch_roster()`][] view (`/fetch_roster`) will either fetch the roster
from the roster sheet or delete the saved roster in the database. All the
fetched emails will also be added to the selected Mailchimp audience with the
appropriate tag, which also validates emails according to Mailchimp's definition
(note: a passing valid email does not guarantee its existence; it simply means
that a given string could pass as a real email).

The main bulk of fetching from the roster sheet lies in the
[`fetch_roster()`][fetch roster helper] helper function. The first row of the
roster spreadsheet is assumed to be the header row. Each following row is then
assumed to have the corresponding values according to the columns of the header
row. A lot of tracking needs to be done to handle repeat user rows, the teams
seen so far, alternates, conflicting weight classes, etc. The log of how each
row is processed is saved to be displayed on the Fetch Roster Log page.

One drawback of the current roster fetching is that user emails are used for
uniqueness. This means that it is impossible to add a user without an email (the
row is skipped), which in turn means that sending a notification to a match
where one the members do not have emails will not work (the match will be
considered invalid). A different way of handling fetching the users, user
identification, and invalid matches is necessary for the system to become more
robust. At the time of implementation, I thought these constraints were useful
for ensuring validity in all steps, but in real world usage, things are never
perfect.

### Templates

All the templates are located in the [`src/templates/`][] folder, organized by
purpose or permission. The most important templates are located in the
[`src/templates/shared/`][] folder; they define the general layout (with imports
of libraries such as Bootstrap and jQuery), include shared CSS and JavaScript,
define the navbar and the various tabs available for certain users, define
common macros used throughout the other templates, and set up the groundwork for
other templates to extend and use. For Jinja-specific rules and guidelines,
please see the [Jinja documentation][].

### Development Tips

#### Log in as anyone

To easily test permissions and pages of different logged in users, add the
following code to `src/views/auth.py` at the top of the
[`log_in()`](src/views/auth.py#L47) function:

```python
if flask.current_app.debug:
    # if in development, allow logging in as anyone
    log_in_as = request.args.get("as", None)
    if log_in_as:
        session["email"] = log_in_as
        return _redirect_last()
```

You will also need to import `flask` (or `from flask import current_app`). Now,
to change the currently logged in user to `someuser@example.com`, direct the URL
to https://localhost:5000/login?as=someuser@example.com. You will then be
redirected back to the same page you were just on, but logged in as the
specified user.

While this code should technically be fine to put in a production version since
it checks whether the current app is in debug mode, I have always left it out of
the committed code to be safe.

#### Disable Mailchimp functions

To make some code run faster as well as to avoid unnecessary or non-get API
calls, you can disable some of the Mailchimp functions by returning an expected
value at the top of the function. For instance, I have been doing the following:

- If [`add_members()`](src/utils/mailchimp_utils.py#L348) is called many times,
  it may result in an error that a user has been added to too many lists
  recently and Mailchimp is going to block them for some time. However, I still
  want to be able to fetch rosters, so I disabled this with:
  ```python
  return None, set()
  ```
- [`create_and_send_campaign()`](src/utils/mailchimp_utils.py#L637) will send
  actual emails, but for a lot of the testing this is not necessary. This can
  be disabled with:
  ```python
  return None, {"id": "campaign"}
  ```
  The returned campaign info must have an `"id"` field because the server logs
  will print it for debugging purposes.
- [`create_and_send_campaign_to_emails()`](src/utils/mailchimp_utils.py#L717)
  will change the contacts for the provided segment, so this can also be
  similarly disabled with:
  ```python
  return None, {"id": "campaign"}
  ```
  Again, the `"id"` field is necessary.

<!-- Reference links -->

<!-- External links -->

[`pipenv`]: https://pipenv.pypa.io/en/stable/
[`black`]: https://black.readthedocs.io/en/stable/
[`isort`]: https://pycqa.github.io/isort/
[`pylint`]: https://pylint.readthedocs.io/en/stable/
[Render]: https://render.com/
[`gunicorn`]: https://gunicorn.org/
[cert tutorial]: https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https
[google authentication tutorial]: https://realpython.com/flask-google-login/
[Flask blueprints]: https://flask.palletsprojects.com/en/2.3.x/blueprints/
[Flask-SQLAlchemy]: https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/
[Flask-Migrate]: https://flask-migrate.readthedocs.io/en/stable/
[Jinja documentation]: https://jinja.palletsprojects.com/en/3.1.x/

<!-- Local files -->

[`Pipfile`]: Pipfile
[`pyproject.toml`]: pyproject.toml
[`build.sh`]: build.sh
[`start.sh`]: start.sh
[`src/runserver.py`]: src/runserver.py
[`migrations/versions/`]: migrations/versions/

<!-- Source code -->

[`src/`]: src/
[`src/db/`]: src/db/
[`src/db/models.py`]: src/db/models.py
[`src/utils/server.py`]: src/utils/server.py
[`src/views/`]: src/views/
[`src/views/auth.py`]: src/views/auth.py
[`src/app.py`]: src/app.py
[`src/config.py`]: src/config.py
[`src/templates/`]: src/templates/

<!-- References -->

[`register_all()`]: src/views/__init__.py#L20
[`AppRoutes`]: src/utils/server.py#L21
[dev database]: src/config.py#L55
[`fetch_matches_info()`]: src/views/notifications.py#L88
[`parse_matches_query()`]: src/utils/notifications_utils.py#L66
[`fetch_match_teams()`]: src/utils/fetch_tms.py#L798
[`matches_info_rows.jinja`]: src/templates/notifications/matches_info_rows.jinja
[`send_match_notification()`]: src/views/notifications.py#L424
[`validate_subject()`]: src/utils/notifications_utils.py#L204
[`send_blast_notification()`]: src/views/notifications.py#L784
[`fetch_roster()`]: src/views/admin.py#L120
[fetch roster helper]: src/utils/fetch_tms.py#339
