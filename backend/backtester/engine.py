import json
import subprocess
import sys
import time
import os
from decimal import Decimal
from django.utils import timezone
from kafka import KafkaConsumer
from backtester.models import BacktestRun, Trade
from backtester.kafka_producer import publish_run_bars
from backtester.metrics import calculate_metrics
from backtester.indicators import get_sma
from backtester.progress import set_progress, clear_progress

KAFKA_BOOTSTRAP = os.environ.get('KAFKA_BOOTSTRAP', 'localhost:9092')

def run_backtest(run_id, code_file_path):
    run = BacktestRun.objects.get(id=run_id)
    run.status = 'running'
    run.save()

    start_time = time.time()
    processed = 0

    cash = Decimal(run.starting_cash)
    shares_held = Decimal('0')
    last_price = None
    last_ts = None
    entry_price = None

    # Publish this run's bars to its own Kafka topic
    topic_name = publish_run_bars(run)

    sma_10 = get_sma(run.symbol, 10, run.start_date, run.end_date)
    sma_50 = get_sma(run.symbol, 50, run.start_date, run.end_date)
    bar_index = 0
    total_bars = len(sma_10)  # same length as the bar set for this run

    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers=KAFKA_BOOTSTRAP,
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

            payload = {
                'bar': bar_dict,
                'indicators': {
                    'sma_10': sma_10[bar_index] if bar_index < len(sma_10) else None,
                    'sma_50': sma_50[bar_index] if bar_index < len(sma_50) else None,
                }
            }
            process.stdin.write(json.dumps(payload) + '\n')
            process.stdin.flush()
            bar_index += 1

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

            if shares_held > 0 and entry_price:
                change_pct = float((price - entry_price) / entry_price)
                if run.stop_loss_pct and change_pct <= -run.stop_loss_pct:
                    decision = 'SELL'
                elif run.take_profit_pct and change_pct >= run.take_profit_pct:
                    decision = 'SELL'

            if decision == 'BUY' and shares_held == 0 and cash > 0:
                slippage = Decimal(str(run.slippage_pct))
                commission = Decimal(str(run.commission_pct))
                fill_price = price * (Decimal('1') + slippage)

                max_allowed = cash * Decimal(str(run.max_position_pct))
                shares_held = max_allowed / fill_price
                cost = shares_held * fill_price
                fee = cost * commission
                total_spent = cost + fee

                Trade.objects.create(run=run, side='BUY', ts=ts, price=fill_price, quantity=shares_held)
                cash = cash - total_spent
                entry_price = fill_price

            elif decision == 'SELL' and shares_held > 0:
                slippage = Decimal(str(run.slippage_pct))
                commission = Decimal(str(run.commission_pct))
                fill_price = price * (Decimal('1') - slippage)  # receive slightly less than quoted close

                proceeds = shares_held * fill_price
                fee = proceeds * commission
                net_proceeds = proceeds - fee

                Trade.objects.create(run=run, side='SELL', ts=ts, price=fill_price, quantity=shares_held)
                cash = net_proceeds
                shares_held = Decimal('0')
                entry_price = None

            processed += 1
            set_progress(run.id, processed, total_bars)
        # Close out any open position at the last known price
        # Close out any open position at the last known price
        if shares_held > 0 and last_price:
            slippage = Decimal(str(run.slippage_pct))
            commission = Decimal(str(run.commission_pct))
            fill_price = last_price * (Decimal('1') - slippage)
            proceeds = shares_held * fill_price
            fee = proceeds * commission
            cash = proceeds - fee
            Trade.objects.create(run=run, side='SELL', ts=last_ts, price=fill_price, quantity=shares_held)
            shares_held = Decimal('0')
            entry_price = None

        run.execution_time_ms = int((time.time() - start_time) * 1000)
        run.bars_processed = processed
        run.final_value = cash
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.save()

        calculate_metrics(run)
        clear_progress(run.id)
    except Exception as e:
        run.status = 'failed'
        run.error_message = f"Unexpected engine error: {str(e)}"
        run.save()
        clear_progress(run.id)
    finally:
        process.stdin.close()
        process.terminate()
        consumer.close()
        import os
        if os.path.exists(code_file_path):
            os.remove(code_file_path)