# LEONIDA / FILES — free Google accounts setup

The website code for Google login and per-user saved-guide sync is installed, but **accounts are not active** until you connect your own Firebase project.

1. Open https://console.firebase.google.com/ and create a project. You can leave Google Analytics disabled. Stay on the **Spark (no-cost)** plan; do not enable billing or Blaze.
2. In **Project settings > Your apps**, register a **Web** app. Copy its **Firebase configuration object** into `firebase-config.js` (replace the four placeholders). This web configuration includes a **public** API key; never use a service-account key.
3. In **Build > Authentication > Sign-in method**, enable **Google** and choose the project support email.
4. In **Authentication > Settings > Authorized domains**, add `nq1james.github.io` (just the domain, not the path). The `firebaseapp.com` project domain should also be authorized.
5. In **Build > Firestore Database**, create a database on the free tier. Open **Rules**, paste the entire contents of `firestore.rules`, and **Publish**. Do not use permissive test rules for production.
6. Commit your completed `firebase-config.js` to GitHub and wait for GitHub Pages to deploy. Open https://nq1james.github.io/gta6features/ and click **SIGN UP / LOG IN > Continue with Google**.
7. Sign in on another device and confirm saved guides sync. If Google redirects fail, confirm the GitHub Pages domain is authorized and that your Firebase web app uses the correct authDomain.

**Security:** Google handles the password. The public Firebase config is safe to include in a website when Authentication authorized domains and Firestore Security Rules are correctly configured. Firestore rules restrict each user to their own saved-guide document. Anonymous bookmarks stay on the device; they are not automatically uploaded to someone else's Google account.

**Cost:** Firebase Spark has usage quotas. The website does not require a paid subscription or billing account. If quotas are exceeded, services can be limited rather than automatically upgrading.
