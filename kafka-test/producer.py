from kafka import KafkaProducer
import time

producer = KafkaProducer(bootstrap_servers='localhost:9092')

for i in range(1, 6):
    msg = f"day {i}"
    producer.send('test-topic', msg.encode('utf-8'))
    print(f"Sent: {msg}")
    time.sleep(1)

producer.flush()