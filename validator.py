import re
import smtplib
import dns.resolver
import csv
import threading
from queue import Queue
from time import time, sleep
from datetime import timedelta
from collections import defaultdict
import random
import string

# Config - adjust these as needed
NUM_THREADS = 50  # Reduced for web environment
NUM_FAKE_CHECKS = 3
SMTP_RETRIES = 3
ENABLE_CATCH_ALL_CHECK = True

def validate_email_format(email):
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

def generate_random_email(domain):
    local_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{local_part}@{domain}"

def validate_domain(domain):
    try:
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(records[0].exchange).rstrip('.')
        return mx_record
    except Exception:
        return None

def smtp_check(mx_record, email, domain):
    try:
        server = smtplib.SMTP(mx_record, timeout=10)
        server.helo()
        server.mail('test@example.com')
        code_real, _ = server.rcpt(email)

        if code_real != 250:
            server.quit()
            return 'Bounce'

        if ENABLE_CATCH_ALL_CHECK:
            catch_all = True
            for _ in range(NUM_FAKE_CHECKS):
                fake_email = generate_random_email(domain)
                code_fake, _ = server.rcpt(fake_email)
                if code_fake != 250:
                    catch_all = False
                    break
            server.quit()
            return 'Catch-All' if catch_all else 'Valid'

        server.quit()
        return 'Valid'

    except (smtplib.SMTPException, Exception):
        return 'SMTP Error'

def validate_email(email):
    if not validate_email_format(email):
        return 'Invalid Format'

    domain = email.split('@')[1]
    mx_record = validate_domain(domain)

    if not mx_record:
        return 'Invalid Domain'

    for _ in range(SMTP_RETRIES):
        result = smtp_check(mx_record, email, domain)
        if result != 'SMTP Error':
            return result
        sleep(1)

    return 'SMTP Error'

def worker(queue, results, status_counter, lock, total):
    while not queue.empty():
        try:
            email = queue.get_nowait()
        except:
            break

        try:
            status = validate_email(email)
        except:
            status = "Unknown Error"

        with lock:
            status_counter[status] += 1
            results.append([email, status])
            if len(results) % 100 == 0:
                print(f"Processed {len(results)}/{total} emails...")

        queue.task_done()

def validate_emails_from_csv(input_path, output_path):
    emails = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get('Email', '').strip() or row.get('email', '').strip()
            if email:
                emails.append(email)

    if not emails:
        return {'error': 'No valid emails found in CSV'}

    total = len(emails)
    print(f"Processing {total} emails...")

    queue = Queue()
    for email in emails:
        queue.put(email)

    status_counter = defaultdict(int)
    results = []
    lock = threading.Lock()

    threads = []
    for _ in range(min(NUM_THREADS, total)):  # Don't create more threads than emails
        t = threading.Thread(target=worker, args=(queue, results, status_counter, lock, total))
        t.daemon = True
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Save results to CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Email', 'Status'])
        writer.writerows(results)

    # Prepare stats for the web interface
    stats = {
        'total': total,
        'valid': status_counter.get('Valid', 0),
        'bounce': status_counter.get('Bounce', 0),
        'catch_all': status_counter.get('Catch-All', 0),
        'invalid_format': status_counter.get('Invalid Format', 0),
        'invalid_domain': status_counter.get('Invalid Domain', 0),
        'smtp_error': status_counter.get('SMTP Error', 0),
        'unknown': status_counter.get('Unknown Error', 0)
    }

    return stats