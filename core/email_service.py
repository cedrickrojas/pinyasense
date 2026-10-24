"""Email service for sending password reset codes and notifications"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

def get_email_config():
    """Get email configuration from environment"""
    return {
        'server': os.getenv('MAIL_SERVER'),
        'port': int(os.getenv('MAIL_PORT', 587)),
        'username': os.getenv('MAIL_USERNAME'),
        'password': os.getenv('MAIL_PASSWORD'),
        'base_url': os.getenv('APP_BASE_URL', 'https://xn--piasense-e3a.tech').rstrip('/'),
        'from_email': os.getenv('MAIL_FROM', os.getenv('MAIL_USERNAME', 'noreply@agripinya.com'))
    }

def send_reset_code_email(to_email, reset_code):
    """Send password reset code via email"""
    config = get_email_config()
    
    # Check if email is configured
    if not all([config['server'], config['username'], config['password']]):
        print("Password reset was not sent: SMTP is not configured.")
        return False
    
    try:
        subject = "🍍 AgriPinya - Password Reset Code"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 2rem; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 2rem; }}
                .code-box {{ background: white; border: 3px solid #10b981; border-radius: 8px; padding: 1.5rem; text-align: center; margin: 1.5rem 0; }}
                .code {{ font-size: 2rem; font-weight: bold; color: #10b981; letter-spacing: 5px; font-family: 'Courier New', monospace; }}
                .footer {{ background: #e5e7eb; color: #666; font-size: 0.9rem; padding: 1rem; text-align: center; border-radius: 0 0 8px 8px; }}
                .badge {{ display: inline-block; background: #10b981; color: white; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.85rem; margin-top: 0.5rem; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🍍 AgriPinya</h1>
                    <p>Smart Pineapple Disease Detection</p>
                </div>
                <div class="content">
                    <h2>Password Reset Request</h2>
                    <p>We received a request to reset your password. Use the code below to create a new password:</p>
                    
                    <div class="code-box">
                        <p style="margin: 0 0 0.5rem 0; color: #666; font-size: 0.9rem;">Your Reset Code:</p>
                        <div class="code">{reset_code}</div>
                        <span class="badge">Valid for 1 hour</span>
                    </div>
                    
                    <p><strong>How to use this code:</strong></p>
                    <ol>
                        <li>Go to AgriPinya login page</li>
                        <li>Click "Forgot Password?"</li>
                        <li>Enter this code: <strong>{reset_code}</strong></li>
                        <li>Create your new password</li>
                    </ol>
                    
                    <p style="color: #999; font-size: 0.9rem; margin-top: 1.5rem;">
                        If you didn't request this email, please ignore it or contact support.
                    </p>
                </div>
                <div class="footer">
                    <p>© 2026 AgriPinya. All rights reserved.</p>
                    <p>This is an automated email, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        AgriPinya - Password Reset Code
        
        We received a request to reset your password. Use this code to create a new password:
        
        {reset_code}
        
        This code is valid for 1 hour.
        
        If you didn't request this email, please ignore it.
        
        AgriPinya - Smart Pineapple Disease Detection
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['from_email']
        msg['To'] = to_email
        
        # Attach both text and HTML versions
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        with smtplib.SMTP(config['server'], config['port'], timeout=15) as server:
            server.starttls()  # Secure connection
            server.login(config['username'], config['password'])
            server.sendmail(config['from_email'], to_email, msg.as_string())
        
        print(f"✓ Reset code sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"✗ Error sending email to {to_email}: {str(e)}")
        return False

def send_welcome_email(to_email, fullname):
    """Send welcome email to new user"""
    config = get_email_config()
    
    if not all([config['server'], config['username'], config['password']]):
        print("Email was not sent: SMTP is not configured.")
        return False
    
    try:
        subject = "🍍 Welcome to AgriPinya!"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 2rem; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 2rem; }}
                .button {{ display: inline-block; background: #10b981; color: white; padding: 0.75rem 1.5rem; text-decoration: none; border-radius: 6px; margin: 1rem 0; }}
                .footer {{ background: #e5e7eb; color: #666; font-size: 0.9rem; padding: 1rem; text-align: center; border-radius: 0 0 8px 8px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🍍 Welcome to AgriPinya!</h1>
                    <p>Smart Pineapple Disease Detection</p>
                </div>
                <div class="content">
                    <h2>Welcome, {fullname}!</h2>
                    <p>Thank you for joining AgriPinya. We're excited to have you on board!</p>
                    
                    <p><strong>What you can do with AgriPinya:</strong></p>
                    <ul>
                        <li>🎥 Detect pineapple diseases using AI</li>
                        <li>📊 Monitor soil moisture and temperature</li>
                        <li>📈 Track your farming data and history</li>
                        <li>💡 Get smart recommendations</li>
                    </ul>
                    
                    <p style="text-align: center;">
                        <a href="{config['base_url']}/dashboard" class="button">Get Started Now</a>
                    </p>
                    
                    <p>If you have any questions, feel free to contact our support team.</p>
                </div>
                <div class="footer">
                    <p>© 2026 AgriPinya. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['from_email']
        msg['To'] = to_email
        
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(config['server'], config['port'], timeout=15) as server:
            server.starttls()
            server.login(config['username'], config['password'])
            server.sendmail(config['from_email'], to_email, msg.as_string())
        
        print(f"✓ Welcome email sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"✗ Error sending welcome email: {str(e)}")
        return False

def send_email_notification(to_email, fullname, notification_message):
    """Send soil moisture alert notification via email"""
    config = get_email_config()
    
    # Check if email is configured
    if not all([config['server'], config['username'], config['password']]):
        print("Email was not sent: SMTP is not configured.")
        return False
    
    try:
        subject = "🚨 AgriPinya - Soil Moisture Alert"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Arial', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #ef4444, #dc2626); color: white; padding: 2rem; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 2rem; }}
                .alert-box {{ background: #fee2e2; border-left: 4px solid #ef4444; padding: 1.5rem; margin: 1.5rem 0; border-radius: 4px; }}
                .alert-title {{ font-size: 1.5rem; font-weight: bold; color: #7f1d1d; margin-bottom: 0.5rem; }}
                .alert-message {{ color: #991b1b; line-height: 1.8; }}
                .footer {{ background: #e5e7eb; color: #666; font-size: 0.9rem; padding: 1rem; text-align: center; border-radius: 0 0 8px 8px; }}
                .action-button {{ display: inline-block; background: #ef4444; color: white; padding: 0.75rem 1.5rem; text-decoration: none; border-radius: 6px; margin-top: 1rem; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚨 Soil Moisture Alert</h1>
                    <p>AgriPinya Notification</p>
                </div>
                <div class="content">
                    <p>Hi {fullname},</p>
                    
                    <div class="alert-box">
                        <div class="alert-title">⚠️ Action Required</div>
                        <div class="alert-message">{notification_message}</div>
                    </div>
                    
                    <p><strong>What should you do?</strong></p>
                    <ul>
                        <li>Check your soil moisture levels immediately</li>
                        <li>Water your pineapple plants if needed</li>
                        <li>Monitor soil conditions closely</li>
                    </ul>
                    
                    <p style="color: #666; font-size: 0.9rem; margin-top: 1.5rem;">
                        This is an automated alert from AgriPinya. If you no longer wish to receive these notifications, please contact support.
                    </p>
                </div>
                <div class="footer">
                    <p>© 2026 AgriPinya. Smart Pineapple Disease Detection.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        AgriPinya - Soil Moisture Alert
        
        Hi {fullname},
        
        {notification_message}
        
        Please check your soil moisture levels and water your plants if needed.
        
        AgriPinya - Smart Pineapple Disease Detection
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['from_email']
        msg['To'] = to_email
        
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(config['server'], config['port'], timeout=15) as server:
            server.starttls()
            server.login(config['username'], config['password'])
            server.sendmail(config['from_email'], to_email, msg.as_string())
        
        print(f"✓ Soil moisture alert sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"✗ Error sending soil moisture alert: {str(e)}")
        return False


def send_report_email(to_email, subject, body_text, attachments=None):
    """Send an email with optional attachments (attachments: dict of filename->bytes).
    Returns True only when SMTP accepted the message.
    """
    config = get_email_config()
    if not all([config['server'], config['username'], config['password']]):
        print("Email was not sent: SMTP is not configured.")
        return False

    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = config['from_email']
        msg['To'] = to_email

        # Attach body
        msg.attach(MIMEText(body_text, 'plain'))

        # Attach files
        if attachments:
            for fname, content in attachments.items():
                part = MIMEBase('application', 'octet-stream')
                if hasattr(content, 'getvalue'):
                    content = content.getvalue()
                if isinstance(content, str):
                    content = content.encode('utf-8')
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{fname}"')
                msg.attach(part)

        with smtplib.SMTP(config['server'], config['port'], timeout=15) as server:
            server.starttls()
            server.login(config['username'], config['password'])
            server.sendmail(config['from_email'], to_email, msg.as_string())

        print(f"✓ Report email sent to {to_email}")
        return True

    except Exception as e:
        print(f"✗ Error sending report email to {to_email}: {str(e)}")
        return False
