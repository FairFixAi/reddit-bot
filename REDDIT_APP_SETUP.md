# How to Get a Reddit Developer App (Step-by-Step)

Use this guide to create your own Reddit application so you can get **Client ID** and **Client Secret** for the Reddit Bot. The client may use it later to create the official app; for now you can use your own for development.

---

## Step 1: Log in to Reddit

1. Go to [reddit.com](https://www.reddit.com) and log in with your account.
2. You need a Reddit account that is at least 30 days old and has some karma (Reddit may require this for API access). If you don’t have one, create an account and wait if needed.

---

## Step 2: Open the App Preferences Page

1. In the top-right, click your **username**.
2. Click **User Settings** (or go to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)).
3. Or go directly: **https://www.reddit.com/prefs/apps**

---

## Step 3: Create an App

1. Scroll down to **"developed applications"**.
2. Click **"create another app..."** or **"create application"**.

---

## Step 4: Fill Out the Form

1. **Name:** Any name (e.g. `Reddit Monitor Bot` or `reddit-bot-dev`). This is only for you.
2. **App type:** Select **"script"**.
   - **script** = backend app that runs with your Reddit account (recommended for a bot that only reads public posts).
   - "web app" is for a site that logs users in with Reddit; "installed app" is for mobile/desktop.
3. **Description:** Optional (e.g. `Bot for monitoring subreddit posts`).
4. **About url:** Leave blank (optional).
5. **Redirect uri:** For a script app, Reddit often requires a redirect URI. Use:  
   **`http://localhost:8080`**  
   (We don’t run a server for OAuth in this project; script app with this placeholder is fine for app-only / client credentials usage if the API allows it. If the form rejects, try `http://localhost` or the exact value Reddit suggests.)
6. Click **"create app"**.

---

## Step 5: Get Your Credentials

After the app is created you’ll see something like:

- **Personal use script** (under the app name) → this is your **Client ID** (short string under the app name).
- **Secret** (sometimes shown as "secret") → this is your **Client Secret**. Click to reveal if it’s hidden.

Copy both:
- **REDDIT_CLIENT_ID** = the "personal use script" value (looks like `aBcDeFgHiJkLmNoP`).
- **REDDIT_CLIENT_SECRET** = the "secret" value.

---

## Step 6: Set the User Agent

Reddit requires a descriptive **User-Agent**. Use your Reddit username:

- **REDDIT_USER_AGENT** = `RedditBot/1.0 (by YOUR_REDDIT_USERNAME)`

Replace `YOUR_REDDIT_USERNAME` with the Reddit account that owns the app (e.g. your main account).

---

## Step 7: Put Values in `.env`

In the project’s `reddit-bot` folder, open `.env` and set:

```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=RedditBot/1.0 (by your_reddit_username)
```

Save the file. Do not commit `.env` or share these values.

---

## If Reddit Won’t Let You Create an App

Sometimes Reddit blocks new app creation (e.g. during API changes or for new accounts). If that happens:

1. Try again later.
2. Ensure your account is in good standing (no recent bans, enough age/karma if required).
3. Use a different browser or clear cookies and try again.
4. For this project, the client (Alan) will create the official app when Reddit allows; you can develop with a temporary app from your side until then and later replace `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` with the client’s credentials.

---

## Replacing With the Client’s Official App Later

When the client provides their own Reddit app:

1. Get from the client: **Client ID** and **Client Secret** (and optionally the Reddit username for the User-Agent).
2. In `.env` (and in the deployment environment variables), set:
   - `REDDIT_CLIENT_ID` = client’s Client ID  
   - `REDDIT_CLIENT_SECRET` = client’s Client Secret  
   - `REDDIT_USER_AGENT` = e.g. `RedditBot/1.0 (by client_reddit_username)` if they specify one.
3. Restart the app / redeploy. No code changes needed.

---

# Reddit Developer / API Application – Q&A (Support Form)

When submitting your Reddit developer app or answering support, use:  
https://support.reddithelp.com/hc/de/requests/new?ticket_form_id=14868593862164

Use the answers below for the application form.

---

### QUESTION 1: What benefit/purpose will the bot/app have for Redditors?

The bot helps improve support for Redditors in specific communities (e.g. r/MechanicAdvice, r/cars, r/AskMechanics) by analyzing public posts to identify recurring topics, sentiment, and trends. The output is used to create weekly summaries and reports that inform better resources and content for those subreddits. It is read-only, does not interact with users or store usernames, and complies with Reddit's API terms.

---

### QUESTION 2: Provide a detailed description of what the Bot/App will be doing on the Reddit platform.

The app is a read-only monitoring tool that uses the official Reddit API. It does not post, comment, vote, message, or otherwise interact with Reddit.

**Behaviour on Reddit:**

1. It requests public listing endpoints (e.g. subreddit "new" listings) for a fixed, predefined list of subreddits (e.g. r/MechanicAdvice, r/cars, r/Cartalk, r/AutoRepair, r/Justrolledintotheshop, r/AskMechanics, r/usedcars, r/whatcarshouldIbuy, r/carproblems, r/enginebuilding).
2. It collects only public post data: post ID, subreddit name, title, and body text. It does not collect, store, or use usernames or any other user-identifying information.
3. It does not access comments, private subreddits, or any data beyond the public post listings for these subreddits.
4. All access is via the Reddit API in line with the API terms and Reddit's platform rules; there is no scraping or use of unofficial methods.

**Off-Reddit use of data:**

1. The post content and metadata are stored in our own database for analysis (e.g. topic and sentiment classification, trend summaries). Results are used only for internal reporting and to improve support and resources for those communities. No Reddit data is resold or used for advertising; no usernames are ever stored or shared.

**Summary:** The app only reads public post listings from the specified subreddits through the official API, stores post content (no usernames) for analysis, and produces aggregate insights. It does not perform any in-platform actions (no posting, commenting, or voting).

---

### QUESTION 3: What is missing from Devvit that prevents building on that platform?

Our use case requires an off-platform pipeline that Devvit is not designed to support:

1. **External infrastructure:** We run a backend service (e.g. on Render) that needs to connect to our own database (Supabase/PostgreSQL), run on a fixed schedule (daily collection, weekly reports), and call third-party APIs (e.g. OpenAI for classification and an email provider for reports). Devvit apps run inside Reddit's runtime and are not meant to own or orchestrate this kind of external, scheduled workflow with our own persistent database and email delivery.

2. **Data retention and processing:** We need to store Reddit post content in our own database, apply a 90-day rolling retention policy, run AI classification on that data, and generate weekly JSON summaries and email reports. That requires long-lived storage, cron-style jobs, and integrations (OpenAI, SMTP/email API) that sit outside Reddit. Devvit's storage and execution model are for apps that run on Reddit, not for this external data collection and reporting pipeline.

3. **Read-only Data API usage:** Our app only needs read-only access to public subreddit listings via the Data API (e.g. to fetch new posts). We do not need Reddit-hosted UI, custom post types, or mod tools. Building on Devvit would not replace the need for API credentials to pull data into our own system; it would add a platform (Devvit) that doesn't address our requirement to run scheduled jobs, maintain our own DB, and send email reports.

So we are not building a Reddit-hosted experience (where Devvit shines); we are building an external monitoring and reporting service that uses the Reddit API as a read-only data source. For that, the Data API with OAuth2 credentials is the appropriate fit, and Devvit does not provide the off-platform scheduling, storage, and integrations we need.

---

### QUESTION 4: Provide a link to source code or platform that will access the API.

https://github.com/developer-vic/REDDIT_PROJECT

---

### QUESTION 5: What subreddits do you intend to use the bot/app in?

MechanicAdvice, cars, Cartalk, AutoRepair, Justrolledintotheshop, AskMechanics, usedcars, whatcarshouldIbuy, carproblems, enginebuilding.

---

### QUESTION 6: If applicable, what username will you be operating this bot/app under?

The developer application is registered under the Reddit account of the project owner (the account used to create the app). The bot uses read-only API access only; it does not post, comment, or operate as a user, and no Reddit usernames are stored in the application.



### RENDER DEPLOYMENT
Please find attached the reddit-bot project as a zip file. It includes the full code for deployment.

What it does: Collects posts from Reddit (RSS or API), stores them in your Supabase database, classifies them with OpenAI, applies 90-day retention, and sends you a weekly email report (HTML + JSON) every Monday to the address you set.

HOST AND RUN ON RENDER:
1. Unzip the file and upload the reddit-bot folder to a new GitHub repository. In Render, create a project, then inside the project create a Background Worker, select "public Git repository" and set the URL to your Github repository URL (if public) or use "Git provider" (if private).

2. Select the stage, git branch to your preference.
Build command: pip install -r requirements.txt
Start command: python main.py

3. Open Environment and add these variables. Use the exact key names and set your own values OR upload the .env from source code:

Set **all** variables from `.env.example` (no empty values). Highlights:

DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@YOUR_PROJECT_REF.supabase.co:5432/postgres
(Prefer the **pooled** URI from Supabase if Render cannot connect — see troubleshooting below.)
OPENAI_API_KEY=sk-proj-your_openai_api_key_here
REPORT_EMAIL_TO=alan@modernenginepros.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_sender_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password

USE_RSS=true
SUBREDDIT_LIST=MechanicAdvice,cars,Cartalk,AutoRepair,AskMechanics,UsedCars,lemonlaw,autobody,askcarsales,buyingacar
RSS_FEED_URLS=DERIVE_FROM_SUBREDDIT_LIST
(or comma-separated full RSS URLs instead of DERIVE_FROM_SUBREDDIT_LIST)

FETCH_INTERVAL_MINUTES=5
CLASSIFICATION_INTERVAL_MINUTES=60
RETENTION_DAYS=90
RETENTION_RUN_INTERVAL_HOURS=24
POSTS_PER_RUN=50
PIPELINE_MAX_BATCH=50
RSS_MAX_POSTS_PER_RUN=50
RSS_DELAY_BETWEEN_FEEDS_SEC=3.5
CLASSIFICATION_BATCH_SIZE=50
RSS_HTTP_MAX_RETRIES=4
RSS_HTTP_RETRY_BASE_SEC=8
RSS_USER_AGENT=YourApp/1.0 (unique string)

WEEKLY_REPORT_DAYS=7
WEEKLY_REPORT_URGENT_SAMPLE_LIMIT=50
WEEKLY_REPORT_FINANCIAL_SAMPLE_LIMIT=50
WEEKLY_REPORT_PROBLEM_VEHICLE_SQL_LIMIT=150

When USE_RSS=true, set Reddit OAuth vars to placeholders (RSS does not use the API):
REDDIT_CLIENT_ID=unused
REDDIT_CLIENT_SECRET=unused
REDDIT_USER_AGENT=RedditBot/1.0 (by your_reddit_username)

When USE_RSS=false, set real REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET and REDDIT_USER_AGENT instead of unused.

4. Deploy. The worker will run continuously: it collects and classifies on schedule, runs retention daily, and sends the weekly report only on Mondays to REPORT_EMAIL_TO.

5. Check: In Supabase, confirm new rows in posts and post_classifications. In Render Logs, you should see collection and classification messages.



#### Troubleshooting: `Network is unreachable` to Supabase (IPv6)

If logs show something like:
`connection to server at "db.xxxxx.supabase.co" (2600:...) port 5432 failed: Network is unreachable`

then DNS resolved Supabase to **IPv6**, and Render’s network path to that address failed. This is an **infrastructure / connection string** issue, not a bug in the Python code.

**Fix (recommended — current Supabase UI):** Supabase moved connection strings into the **Connect** panel (not a buried “Connection string” submenu under Database settings).

1. Open your project in the [Supabase Dashboard](https://supabase.com/dashboard).
2. Click **Connect** at the top of the project page (green / primary button).
3. In the Connect dialog, choose the connection type:
   - **Session pooler** (Supavisor session mode) — **use this for Render** when the direct URL fails with IPv6 / “Network is unreachable”. It uses a host like `aws-0-<region>.pooler.supabase.com` on port **5432** and a username like `postgres.<project-ref>` (copy exactly what the dashboard shows).
   - **Transaction pooler** — for short-lived / serverless clients; often `db.<project-ref>.supabase.co` port **6543** with user `postgres`. This app is a long-running worker; **prefer Session pooler** unless Supabase’s docs for your case say otherwise.
4. Copy the **URI** (or connection string) from that panel — do not hand-edit host/user unless you know what you’re doing.
5. Set it as `DATABASE_URL` on Render (and in `.env` if local). Restart the worker.

Official guide (methods, ports, examples):  
https://supabase.com/docs/guides/database/connecting-to-postgres  
