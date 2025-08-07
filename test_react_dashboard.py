#!/usr/bin/env python3
"""
Quick test script to submit an alert and check if ReAct dashboard updates are working.
"""

import asyncio
import json
import requests
import time
from typing import Dict, Any

BACKEND_URL = "http://localhost:8000"

def submit_test_alert() -> str:
    """Submit a simple Kubernetes test alert."""
    alert_data = {
        "alert_type": "kubernetes",
        "timestamp": int(time.time() * 1000000),  # microseconds
        "data": {
            "namespace": "default",
            "pod_name": "test-pod-react-demo",
            "status": "Pending",
            "environment": "staging",
            "cluster": "test-cluster"
        },
        "runbook": "https://github.com/example/runbooks/blob/main/k8s-pod-pending.md"
    }
    
    print(f"🚀 Submitting test alert to {BACKEND_URL}/submit-alert")
    print(f"📝 Alert data: {json.dumps(alert_data, indent=2)}")
    
    try:
        response = requests.post(f"{BACKEND_URL}/submit-alert", json=alert_data)
        response.raise_for_status()
        result = response.json()
        
        alert_id = result.get("alert_id")
        print(f"✅ Alert submitted successfully!")
        print(f"📋 Alert ID: {alert_id}")
        print(f"📊 Status: {result.get('status')}")
        print(f"💬 Message: {result.get('message')}")
        
        return alert_id
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error submitting alert: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📄 Response: {e.response.text}")
        return None

def check_alert_status(alert_id: str) -> Dict[str, Any]:
    """Check the current status of an alert."""
    try:
        response = requests.get(f"{BACKEND_URL}/status/{alert_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error checking status: {e}")
        return {}

def main():
    print("🧪 Testing ReAct Dashboard Updates")
    print("=" * 50)
    
    # Submit test alert
    alert_id = submit_test_alert()
    if not alert_id:
        print("❌ Failed to submit alert")
        return
    
    print(f"\n🔍 Monitor the dashboard at: http://localhost:5173")
    print(f"🔍 You should see ReAct reasoning updates in real-time for alert: {alert_id}")
    print("\n📊 Expected to see:")
    print("  • ReAct Analysis Active badge")
    print("  • Iteration counters (Iteration 1, 2, 3...)")
    print("  • Latest reasoning steps updating live")
    print("  • 'X completed' iteration badges")
    
    print(f"\n⏰ Checking status every 5 seconds for 2 minutes...")
    
    for i in range(24):  # Check for 2 minutes
        print(f"\n--- Check {i+1}/24 ---")
        status = check_alert_status(alert_id)
        
        if status:
            current_status = status.get("status", "unknown")
            progress = status.get("progress", 0)
            current_step = status.get("current_step", "N/A")
            
            print(f"📊 Status: {current_status}")
            print(f"📈 Progress: {progress}%")
            print(f"🔧 Step: {current_step}")
            
            # Check for ReAct fields
            react_enabled = status.get("react_enabled")
            current_iteration = status.get("current_iteration")
            total_iterations = status.get("total_iterations")
            latest_reasoning_step = status.get("latest_reasoning_step")
            
            if react_enabled:
                print(f"🧠 ReAct: ENABLED")
                if current_iteration:
                    print(f"🔄 Current Iteration: {current_iteration}")
                if total_iterations:
                    print(f"✅ Completed Iterations: {total_iterations}")
                if latest_reasoning_step:
                    step_type = latest_reasoning_step.get("step_type", "unknown")
                    reasoning_text = latest_reasoning_step.get("reasoning_text", "")[:100]
                    print(f"💭 Latest: {step_type} - {reasoning_text}...")
            else:
                print(f"🧠 ReAct: Not enabled or not started yet")
            
            if current_status in ["completed", "failed"]:
                print(f"\n🏁 Alert processing finished with status: {current_status}")
                break
        else:
            print("❌ Could not retrieve status")
        
        time.sleep(5)
    
    print(f"\n🎯 Test completed!")
    print(f"📋 Final alert ID for reference: {alert_id}")

if __name__ == "__main__":
    main()