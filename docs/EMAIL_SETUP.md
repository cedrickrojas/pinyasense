# Email Integration Setup Guide

## Overview

AgriPinya now has **email integration** to send:
- 📧 Password reset codes
- 👋 Welcome emails to new users
- 📬 Future notifications and alerts

## Quick Start (Testing Mode)

If you **don't configure email**, the system will:
- ✓ Show reset codes in the browser modal
- ✓ Log codes to the console
- ✓ Display messages in the app

This is perfect for **testing and development**.

## Enable Email Sending

### Step 1: Choose an Email Provider

Pick one of these **free or low-cost** options:

#### 1️⃣ **Gmail (Recommended for Testing)**

Best for development - free and reliable.

**Setup:**
1. Go to [Google Account Settings](https://myaccount.google.com/)
2. Click "Security" (left menu)
3. Enable 2-Step Verification if not already done
4. Search for "App passwords" in the search bar
5. Select "Mail" and "Windows Computer"
6. Google will generate a 16-character password - **copy it**

**Add to `.env`:**
```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-16-char-app-password
MAIL_FROM=noreply@yourdomain.com
```

---

#### 2️⃣ **SendGrid (Best for Production)**

Free tier: 100 emails/day forever.

**Setup:**
1. Sign up at [SendGrid](https://sendgrid.com)
2. Create an API key: Settings → API Keys → Create API Key
3. Copy the API key

**Add to `.env`:**
```env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=SG.your-api-key-here
MAIL_FROM=noreply@yourdomain.com
```

---

#### 3️⃣ **Mailgun (Great for Developers)**

Free tier: 1,000 emails/month.

**Setup:**
1. Sign up at [Mailgun](https://www.mailgun.com)
2. Verify your domain
3. Go to Domain → SMTP Credentials
4. Copy the SMTP credentials

**Add to `.env`:**
```env
MAIL_SERVER=smtp.mailgun.org
MAIL_PORT=587
MAIL_USERNAME=postmaster@yourdomain.mailgun.org
MAIL_PASSWORD=your-mailgun-password
MAIL_FROM=noreply@yourdomain.mailgun.org
```

---

#### 4️⃣ **Brevo (France-based)**

Free tier: 300 emails/day.

**Setup:**
1. Sign up at [Brevo](https://www.brevo.com)
2. Go to Settings → SMTP & API
3. Enable SMTP and copy credentials

**Add to `.env`:**
```env
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-brevo-smtp-password
MAIL_FROM=noreply@yourdomain.com
```

---

### Step 2: Create `.env` File

1. **Copy the example:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env`:**
   ```bash
   nano .env
   # or use your preferred editor
   ```

3. **Paste your email provider settings**

### Step 3: Install Dependencies

The required package is already in `requirements.txt`, but make sure it's installed:

```bash
pip install python-dotenv
```

### Step 4: Restart the App

```bash
python app.py
```

## Testing Email Integration

### Test 1: Check Console for Confirmation

When you use "Forgot Password", you should see:

```
✓ Reset code sent to user@example.com
```

Or if email fails:

```
✗ Error sending email...
[Code shown in console as fallback]
```

### Test 2: Check Your Email Inbox

1. Go to http://localhost:5000/login
2. Click "Forgot Password?"
3. Enter your email address
4. Wait a few seconds
5. **Check your inbox** (and spam folder)

You should see:
- 📩 Email from `MAIL_FROM` address
- 🔑 Your 6-character reset code
- ✅ Clean, professional template

### Test 3: Verify Welcome Email

1. Sign up on http://localhost:5000/signup
2. Use your real email
3. Check if you received a welcome email

## Troubleshooting

### Email Not Sending?

**Check:**
1. Is `.env` file in the project root?
   ```bash
   ls -la .env
   ```

2. Are all email settings filled in `.env`?
   ```bash
   grep MAIL .env
   ```

3. Is the app restarted after `.env` changes?
   ```bash
   # Restart the app
   python app.py
   ```

4. Check app console for error messages

### Gmail App Password Not Working?

- Make sure you used the **16-character password**, not your regular Gmail password
- Verify 2-Step Verification is enabled
- Try regenerating the App Password

### SendGrid Not Working?

- Verify the domain is added and verified
- Check the API key is correct
- Make sure SMTP username is literally "apikey"

### Email Lands in Spam?

This is normal for development. Add these to headers to help:
- Use a professional from address
- Add SPF/DKIM records for your domain
- Test with major providers like Gmail

## File Structure

```
agripinya/
├── email_service.py           ✅ Email sending module
├── app.py                     ✅ API routes (updated)
├── auth.py                    ✅ Password reset logic
├── requirements.txt           ✅ Dependencies
├── .env.example               ✅ Configuration template
├── .env                       ✅ Your configuration (create this)
└── templates/
    ├── login.html            ✅ Forgot password modal
    └── signup.html           ✅ Registration form
```

## Email Features

### 1. Password Reset Email

When user clicks "Forgot Password?":
- ✉️ Receives email with 6-character code
- 🔐 Code expires in 1 hour
- 🎨 Beautiful HTML template
- 📱 Mobile-responsive

### 2. Welcome Email

When user signs up:
- 👋 Personalized greeting
- 🎯 What they can do with AgriPinya
- 🚀 Call-to-action button

## Environment Variables Reference

| Variable | Example | Description |
|----------|---------|-------------|
| `MAIL_SERVER` | `smtp.gmail.com` | SMTP server address |
| `MAIL_PORT` | `587` | SMTP port (587 for TLS, 465 for SSL) |
| `MAIL_USERNAME` | `your-email@gmail.com` | Email account username |
| `MAIL_PASSWORD` | `your-app-password` | Email account password or API key |
| `MAIL_FROM` | `noreply@agripinya.com` | Sender email address |

## Security Best Practices

1. **Never commit `.env` to Git**
   ```bash
   # .env is already in .gitignore
   cat .gitignore | grep env
   ```

2. **Use App-Specific Passwords**
   - Don't use your main password
   - Gmail, Brevo, and others offer app-specific passwords

3. **Rotate API Keys Regularly**
   - Change SendGrid API keys monthly
   - Revoke old keys

4. **Monitor Email Usage**
   - Check your provider's dashboard
   - Watch for suspicious activity

## Future Enhancements

- [ ] Email templates customization
- [ ] Scheduled email notifications
- [ ] Email delivery tracking
- [ ] Unsubscribe management
- [ ] Multi-language support
- [ ] SMS integration as fallback

## Support

If emails aren't working:

1. **Check the console** - look for error messages
2. **Check `.env` file** - verify all settings
3. **Test credentials** - try connecting manually with SMTP
4. **Check email logs** - look at your provider's dashboard
5. **Try fallback mode** - codes still show in browser/console

---

Happy emailing! 📧🍍
