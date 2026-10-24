#!/usr/bin/env python3
"""
Firebase Setup Guide and Integration Test
"""

def print_setup_guide():
    guide = """
╔════════════════════════════════════════════════════════════════╗
║          AgriPinya Firebase Integration Guide                  ║
╚════════════════════════════════════════════════════════════════╝

📋 STEP 1: Create Firebase Project
═════════════════════════════════════════════════════════════════
1. Go to Firebase Console: https://console.firebase.google.com
2. Click "Add project" and enter project name
3. Select your region
4. Click "Create project"

📋 STEP 2: Enable Realtime Database
═════════════════════════════════════════════════════════════════
1. In Firebase Console, open your project
2. Go to "Realtime Database" from left menu
3. Click "Create Database"
4. Choose region (same as project)
5. Start in TEST mode for development
   ⚠️  Make sure to set security rules before production!

📋 STEP 3: Create Service Account Key
═════════════════════════════════════════════════════════════════
1. Go to "Project Settings" (gear icon)
2. Click "Service Accounts" tab
3. Click "Generate New Private Key"
4. Save the JSON file as: serviceAccountKey.json
5. Place it in your project root directory
   ✅ IMPORTANT: Never commit this file to Git!

📋 STEP 4: Get Database URL
═════════════════════════════════════════════════════════════════
1. Open Realtime Database
2. Copy the URL (looks like: https://your-project.firebaseio.com)

📋 STEP 5: Update .env File
═════════════════════════════════════════════════════════════════
Copy .env.example to .env and update:

  FIREBASE_SERVICE_ACCOUNT_KEY=./serviceAccountKey.json
  FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
  FIREBASE_STORAGE_BUCKET=your-project.appspot.com
  ENABLE_FIREBASE=true

📋 STEP 6: Install Firebase Dependencies
═════════════════════════════════════════════════════════════════
  pip install -r requirements.txt

📋 STEP 7: Test Firebase Connection
═════════════════════════════════════════════════════════════════
  Run this script with --test flag:
  python -m scripts.maintenance.firebase_setup --test

📋 DATABASE STRUCTURE
═════════════════════════════════════════════════════════════════
{
  "users": {
    "user_id": {
      "profile": {
        "email": "...",
        "fullname": "..."
      },
      "detections": {
        "timestamp": {
          "disease": "...",
          "confidence": 0.95,
          "severity": "...",
          "media_type": "image"
        }
      },
      "sensors": {
        "soil_moisture": {
          "data": {
            "timestamp": {
              "value": 65,
              "unit": "%"
            }
          }
        }
      }
    }
  },
  "detections": { ... },
  "sensors": { ... }
}

🔒 SECURITY RULES (for Production)
═════════════════════════════════════════════════════════════════
Copy these rules to Firebase Console:

{
  "rules": {
    "users": {
      "$uid": {
        ".read": "$uid === auth.uid",
        ".write": "$uid === auth.uid",
        ".validate": "newData.hasChildren(['profile'])"
      }
    },
    "detections": {
      "$detection": {
        ".read": true,
        ".write": false
      }
    }
  }
}

✅ SUCCESS Indicators
═════════════════════════════════════════════════════════════════
✓ Script runs without errors
✓ Data appears in Firebase Console
✓ Queries return correct results
✓ User data is properly isolated

⚠️  TROUBLESHOOTING
═════════════════════════════════════════════════════════════════
Problem: "credentials.json not found"
→ Ensure service account key is in correct location

Problem: "Permission denied"
→ Check Firebase security rules

Problem: "Database URL is invalid"
→ Verify URL format and project name

Problem: "ModuleNotFoundError: firebase_admin"
→ Run: pip install firebase-admin

📚 USEFUL RESOURCES
═════════════════════════════════════════════════════════════════
- Firebase Docs: https://firebase.google.com/docs
- Python Admin SDK: https://firebase.google.com/docs/database/admin/start
- Security Rules: https://firebase.google.com/docs/database/security

════════════════════════════════════════════════════════════════════
"""
    print(guide)

def test_firebase_connection():
    """Test Firebase connection"""
    print("\n🧪 Testing Firebase Connection...")
    print("=" * 60)
    
    try:
        from core.firebase_manager import FirebaseManager
        import os
        from dotenv import load_dotenv
        
        # Load env vars
        load_dotenv()
        
        # Check if service account key exists
        service_account_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')
        if not service_account_key or not os.path.exists(service_account_key):
            print(f"❌ Service account key not found at: {service_account_key}")
            print("   Please follow setup guide above")
            return False
        
        # Create Firebase manager
        config = {
            'service_account_key': service_account_key,
            'database_url': os.getenv('FIREBASE_DATABASE_URL'),
            'storage_bucket': os.getenv('FIREBASE_STORAGE_BUCKET', '')
        }
        
        fm = FirebaseManager(config)
        
        if not fm.is_connected():
            print("❌ Failed to connect to Firebase")
            return False
        
        print("✅ Connected to Firebase")
        
        # Test write
        print("\n📝 Testing write operation...")
        test_data = {
            'timestamp': '2026-03-04_120000',
            'disease': 'Healthy',
            'confidence': 0.95,
            'severity': 'None'
        }
        
        result = fm.save_detection_result(test_data)
        if result:
            print("✅ Write operation successful")
        else:
            print("❌ Write operation failed")
            return False
        
        # Test read
        print("\n📖 Testing read operation...")
        results = fm.get_detection_results(limit=5)
        print(f"✅ Read successful - Retrieved {len(results)} records")
        
        # Test statistics
        print("\n📊 Testing aggregation...")
        stats = fm.aggregate_statistics()
        print(f"✅ Total detections: {stats.get('total_detections', 0)}")
        
        print("\n" + "=" * 60)
        print("✅ All Firebase tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Run: pip install firebase-admin python-dotenv")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == '__main__':
    import sys
    
    print_setup_guide()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        test_firebase_connection()
    else:
        print("\n💡 To test Firebase connection, run:")
        print("   python -m scripts.maintenance.firebase_setup --test")
