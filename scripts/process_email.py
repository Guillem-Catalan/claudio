import sys

from src.pipelines.process_email.run import run

if __name__ == "__main__":
    email_id = sys.argv[1]
    run(email_id=email_id)
