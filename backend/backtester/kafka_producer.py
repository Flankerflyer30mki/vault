import json
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from backtester.models import Bar


def create_topic_if_needed(topic_name):
    admin = KafkaAdminClient(bootstrap_servers='localhost:9092')
    existing_topics = admin.list_topics()
    if topic_name not in existing_topics:
        admin.create_topics([NewTopic(name=topic_name, num_partitions=1, replication_factor=1)])
    admin.close()


def publish_run_bars(run):
    topic_name = f"run-{run.id}-bars"
    create_topic_if_needed(topic_name)

    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    bars = Bar.objects.filter(
        symbol=run.symbol,
        ts__date__gte=run.start_date,
        ts__date__lte=run.end_date
    ).order_by('ts')

    for bar in bars:
        message = {
            'date': bar.ts.isoformat(),
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': bar.volume
        }
        producer.send(topic_name, message)

    producer.send(topic_name, {'end': True})  # sentinel: tells the consumer the stream is done
    producer.flush()
    producer.close()

    return topic_name