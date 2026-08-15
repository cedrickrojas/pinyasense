#!/usr/bin/env python3
"""Test script to trigger SMS notification"""
import sys
sys.path.insert(0, '/home/voicebrain/agripinya')

from core.sensor_monitor import sensor_monitor

print("Testing SMS notification...")
print("Checking for 3-day dry soil and sending SMS to registered users...\n")

sensor_monitor.check_and_notify_all_users(dry_days=3)

print("\nDone! Check your phone for SMS.")
