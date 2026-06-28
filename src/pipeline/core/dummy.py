import sys
import json
import time

def send(obj: dict):
    print(json.dumps(obj), flush=True)

def main():
    send({"type": "log", "text": "Backend ready"})

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            cmd = json.loads(raw_line)
        except json.JSONDecodeError:
            send({"type": "error", "text": "Bad JSON received"})
            continue

        action = cmd.get("action")

        if action == "ping":
            send({"type": "log", "text": "pong"})

        elif action == "run_scan":
            send({"type": "log", "text": f"Starting scan: {cmd.get('name', 'unnamed')}"})
        
            phases = [
                (0.00, "Phase 1: Capture"),
                (0.25, "Phase 2: Masking"),
                (0.50, "Phase 3: Spatial"),
                (0.75, "Phase 4: Geometry"),
                (1.00, "Complete"),
            ]

            for value, label in phases:
                time.sleep(1)
                send({"type": "progress", "value": value, "label": label})
                send({"type": "log", "text": f"Done: {label}"})

            send({"type": "done", "data": {"run_name": cmd.get("name", "unnamed")}})

        else:
            send({"type": "error", "text": f"Unknown action: {action}"})

    send({"type": "log", "text": "Backend exiting"})


if __name__ == "__main__":
    main()
