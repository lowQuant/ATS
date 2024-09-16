# strategy_manager/strategy_manager.py

import importlib.util
import os, queue, asyncio, threading
from multiprocessing import Process
from data_and_research.utils import fetch_strategies
from gui.log import add_log
from broker.trademanager import TradeManager
from broker import connect_to_IB, disconnect_from_IB

class StrategyManager:
    def __init__(self):
        self.ib_client_id = 0
        self.ib_client = connect_to_IB(clientId = self.ib_client_id)
        self.strategy_processes = []
        self.strategies = []
        self.trade_manager = TradeManager(ib_client=self.ib_client)

        # Create a queue for thread safe editing of shared resources (e.g. updating available cash etc.)
        self.message_queue = queue.Queue()
        self.message_processor_thread = threading.Thread(target=self.process_messages)
        self.message_processor_thread.daemon = True
        self.message_processor_thread.start()

        self.load_strategies()
        #TODO: only start ocne all strategies are loaded
        #TODO: load data before

    def load_strategies(self):
        strategy_dir = "strategy_manager/strategies"
        strategy_names, self.strategy_df = fetch_strategies()
        active_filenames = set(self.strategy_df[self.strategy_df["active"] == "True"]['filename'])

        if strategy_names:
            strategy_files = [f for f in self.strategy_df['filename'] if f in os.listdir(strategy_dir) and f in active_filenames]
            for file in strategy_files:
                strategy_path = os.path.join(strategy_dir, file)
                module_name = file[:-3]
                print("Loading strategy:", module_name)

                try:
                    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    if hasattr(module, 'Strategy'):
                        print(f"Instantiating strategy: {module_name}")
                        # Note: Each strategy now needs its own IB client instance
                        self.ib_client_id += 1 # returning a new client id
                        strategy_instance = module.Strategy(self.ib_client, self, self.trade_manager)
                        self.strategies.append(strategy_instance)
                    else:
                        print(f"No 'Strategy' class found in {module_name}")
                except Exception as e:
                    print(f"Error loading strategy {module_name}: {e}")

            print("Loaded strategies:", [type(s).__name__ for s in self.strategies])

    def start_all(self):
        for strategy in self.strategies:
            if hasattr(strategy, 'run'):
                # Start each strategy in its own process
                process = Process(target=strategy.run)
                process.start()
                self.strategy_processes.append(process)
            else:
                print(f"Strategy {type(strategy).__name__} does not have a run method.")

    def stop_all(self):
        for process in self.strategy_processes:
            process.terminate()
            process.join()
        # Disconnect StrategyManager from ib
        disconnect_from_IB(self.ib_client)

    def process_messages(self):
        while True:
            message = self.message_queue.get(block=True)
            if message['type'] == 'order':
                self.notify_order_placement(message['strategy'], message['trade'])
            elif message['type'] == 'fill':
                self.handle_fill_event(message['strategy'], message['trade'], message['fill'])
            elif message['type'] == 'status_change':
                # add_log(f"{message['status']}")
                self.handle_status_change(message['strategy'], message['trade'], message['status'])
            # Add more message types as needed
            self.message_queue.task_done()

    def handle_fill_event(self, strategy_symbol, trade, fill):
        # Implement fill event handling logic
        add_log(f"Order filled for {strategy_symbol}: {fill}")

    def handle_status_change(self, strategy_symbol, trade, status):
        # Implement status change handling logic
        add_log(f"{status}: {trade.order}")

    def update_on_trade(self, strategy, trade_details):
        strategy_name = type(strategy).__name__
        # Calculate new cash position
        new_cash_position = self.calculate_cash_position(strategy_name, trade_details)
        
        # Update database
        self.update_database(strategy_name, trade_details, new_cash_position)

    def calculate_cash_position(self, strategy_name, trade_details):
        # Implement cash position calculation logic
        new_cash_position = 0
        return new_cash_position

    def update_database(self, strategy_name, trade_details, new_cash_position):
        # Implement database update logic
        # Use ArcticDB to update the "portfolio" library with the new trade and cash position
        pass