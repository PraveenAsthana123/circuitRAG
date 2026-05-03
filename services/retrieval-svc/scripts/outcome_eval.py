from datetime import UTC, datetime


def report():
    print({"timestamp": datetime.now(UTC).isoformat(), "status": "OK"})

def contract():
    print("Contract OK")

if __name__ == "__main__":
    import sys
    if "report" in sys.argv:
        report()
    elif "contract" in sys.argv:
        contract()
