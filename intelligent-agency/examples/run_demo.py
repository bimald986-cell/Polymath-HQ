"""Quick demo: build the agency and route a few sample requests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import build_agency

SAMPLES = [
    "how do I fertilise my tomato crop",
    "write a lesson plan about fractions",
    "debug this python api that returns 500 errors",
    "analyse whether Tesla stock is a buy",
    "plan a social media campaign for a new coffee brand",
    "automate sending a weekly report by email",
    "design a circuit to read a temperature sensor",
]


def main():
    president = build_agency()
    print(president.tree())
    print("=" * 60)
    for q in SAMPLES:
        res = president.handle(q)
        print(f"\nQ: {q}")
        print(f"   -> {res['director']} / {res['agent']}")


if __name__ == "__main__":
    main()
