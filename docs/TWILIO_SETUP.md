# Twilio SMS Setup Guide for AgriPinya

## Step 1: Create a Twilio Account
1. Go to https://www.twilio.com/
2. Click **Sign Up** (top right)
3. Enter your email, password, and verify
4. Complete phone verification
5. Accept terms and create account

## Step 2: Get Your Twilio Credentials

### Find Your Account SID and Auth Token:
1. Log in to [Twilio Console](https://www.twilio.com/console)
2. On the main dashboard, you'll see:
   - **Account SID** (looks like: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
   - **Auth Token** (looks like a long alphanumeric string)
3. Click the eye icon next to Auth Token to reveal it
4. **Copy both values** - you'll need them in the next step

### Get Your Twilio Phone Number:
1. In Twilio Console, go to **Phone Numbers** (left sidebar)
2. Click **Get a Number** (or use existing if you have one)
3. Select your country and click **Search**
4. Choose a number (you'll get a trial one for free)
5. Copy the phone number (format: `+1234567890`)

## Step 3: Configure Environment Variables

### Option A: Using `.env` file (Recommended)
1. Copy the template:
   ```bash
   cp .env.twilio.example .env
   ```

2. Edit `.env` and fill in your credentials:
   ```bash
   nano .env
   ```

3. Replace the placeholders:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_actual_auth_token_here
   TWILIO_FROM_NUMBER=+1234567890
   ```

4. Save and exit (Ctrl+X, Y, Enter if using nano)

### Option B: Using Command Line
```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token_here"
export TWILIO_FROM_NUMBER="+1234567890"
```

## Step 4: Add Phone Numbers to users.json

Users must have a valid phone number in `users.json` to receive notifications.

Example:
```json
{
  "agripinyaa@gmail.com": {
    "fullname": "Agripinya",
    "email": "agripinyaa@gmail.com",
    "password": "...",
    "phone": "+639171234567",
    "created_at": "...",
    "last_login": "..."
  }
}
```

**Phone format:** `+[country_code][number]`
- Philippines: `+63` (e.g., `+639171234567`)
- USA: `+1` (e.g., `+12125551234`)
- Other countries: Use international format

## Step 5: Test the SMS System

### Start your Flask app:
```bash
python3 app.py
```

### Trigger a soil moisture reading:
```bash
curl http://localhost:5000/api/sensors/soil-moisture
```

### Expected Behavior:
- If soil is DRY for 3+ consecutive days and phone number is set → **SMS sent!**
- If Twilio is not configured → System logs the message (for testing)

## Step 6: Verify It Works

1. Check your phone for an SMS message from your Twilio number
2. Message format:
   ```
   SYSTEM ALERT: Soil moisture critically low. Ang pinya ay nakaramas ng 3 araw na dryness. I-activate na ang irrigation system.
   ```

## Troubleshooting

### "No SMS received"
- Verify phone number is correct in `users.json`
- Check that Twilio credentials are set correctly
- Ensure soil data shows DRY status for 3+ days
- Check `notifications.json` to see if SMS was marked as sent

### "Auth Error" or "Invalid credentials"
- Double-check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
- Copy from console again (don't miss any characters)
- Make sure Auth Token is not just a prefix

### "Invalid phone number"
- Use international format: `+[country_code][number]`
- Remove spaces, dashes, or parentheses
- Verify with your carrier

## Optional: Custom SMS Message

Edit `.env` to customize the message:
```
SOIL_DRY_NOTIFICATION_MESSAGE="Custom alert: soil dry for {dry_days} days. Water now!"
```

The `{dry_days}` placeholder will be replaced with the actual number of days.

## Security Notes

⚠️ **Never commit `.env` to Git!**
- Add `.env` to `.gitignore` if not already there
- Keep your Auth Token secret
- Regenerate token if accidentally exposed

## Support

For Twilio issues, visit: https://support.twilio.com/
For AgriPinya issues, check logs in the terminal where Flask is running.
