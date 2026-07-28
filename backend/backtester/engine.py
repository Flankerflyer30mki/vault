import json
import subprocess
import sys
from decimal import Decimal
from django.utils import timezone
from kafka import KafkaConsumer
from backtester.models import BacktestRun, Trade
from backtester.kafka_producer import publish_run_bars


def run_backtest(run_id, code_file_path):
    run = BacktestRun.objects.get(id=run_id)
    run.status = 'running'
    run.save()

    cash = Decimal(run.starting_cash)
    shares_held = Decimal('0')
    last_price = None
    last_ts = None

    # Publish this run's bars to its own Kafka topic
    topic_name = publish_run_bars(run)

    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers='localhost:9092',
        auto_offset_reset='earliest',
        group_id=f'engine-run-{run.id}',
        value_deserializer=lambda v: json.loads(v.decode('utf-8'))
    )

    process = subprocess.Popen(
        [sys.executable, 'backtester/sandbox_runner.py', code_file_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        for message in consumer:
            bar_dict = message.value

            if bar_dict.get('end'):
                break  # sentinel reached, stream is done

            process.stdin.write(json.dumps(bar_dict) + '\n')
            process.stdin.flush()

            response_line = process.stdout.readline()
            response = json.loads(response_line)

            if 'error' in response:
                run.status = 'failed'
                run.error_message = response['error']
                run.save()
                process.kill()
                consumer.close()
                return

            decision = response['decision']
            price = Decimal(str(bar_dict['close']))
            ts = bar_dict['date']
            last_price = price
            last_ts = ts

            if decision == 'BUY' and shares_held == 0 and cash > 0:
                shares_held = cash / price
                Trade.objects.create(run=run, side='BUY', ts=ts, price=price, quantity=shares_held)
                cash = Decimal('0')

            elif decision == 'SELL' and shares_held > 0:
                cash = shares_held * price
                Trade.objects.create(run=run, side='SELL', ts=ts, price=price, quantity=shares_held)
                shares_held = Decimal('0')

        # Close out any open position at the last known price
        if shares_held > 0 and last_price:
            cash = shares_held * last_price
            Trade.objects.create(run=run, side='SELL', ts=last_ts, price=last_price, quantity=shares_held)
            shares_held = Decimal('0')

        run.final_value = cash
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.save()

    finally:
        process.stdin.close()
        process.terminate()
        consumer.close()