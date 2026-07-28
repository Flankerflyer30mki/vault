from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'test-topic',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    group_id='test-group'
)

print("Listening for messages...")
for message in consumer:
    print(f"Received: {message.value.decode('utf-8')}")