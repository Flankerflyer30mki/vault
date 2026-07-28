import json
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'bar-replay',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    group_id='vault-engine'
)

print("Engine listening for bars...")
for message in consumer:
    bar = json.loads(message.value.decode('utf-8'))
    print(f"Received: {bar['ts']} close={bar['close']}")