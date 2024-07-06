import asyncio
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.clock import mainthread
from bleak import BleakScanner, BleakClient
import threading
from concurrent.futures import ThreadPoolExecutor

MAX_PACKET_SIZE = 244  # STM32WB55 typical maximum payload size in bytes
NUM_PACKETS = 2000
PACKET_SIZE = 244
MAX_WORKERS = 100

class SpeedTest:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.send_start_time = None
        self.send_end_time = None
        self.receive_start_time = None
        self.receive_end_time = None
        self.total_bytes_sent = 0
        self.total_bytes_received = 0
        self.receive_times = []

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()
        self.show_results()

    def start_sending(self):
        self.send_start_time = time.time()

    def end_sending(self):
        self.send_end_time = time.time()

    def start_receiving(self):
        self.receive_start_time = time.time()

    def end_receiving(self):
        self.receive_end_time = time.time()

    def add_data_sent(self, data_size):
        self.total_bytes_sent += data_size

    def add_data_received(self, data_size, receive_time):
        self.total_bytes_received += data_size
        self.receive_times.append(receive_time)

    def show_results(self):
        if self.start_time and self.end_time:
            total_duration = self.end_time - self.start_time
            send_duration = self.send_end_time - self.send_start_time if self.send_end_time and self.send_start_time else 0
            receive_duration = self.receive_end_time - self.receive_start_time if self.receive_end_time and self.receive_start_time else 0
            avg_receive_time = sum(self.receive_times) / len(self.receive_times) if self.receive_times else 0
            result_text = (
                f"Total bytes sent: {self.total_bytes_sent} bytes\n"
                f"Total time sending: {send_duration:.2f} seconds\n"
                f"Total time receiving: {receive_duration:.2f} seconds\n"
                f"Total duration: {total_duration:.2f} seconds\n"
                f"Average receive time per packet: {avg_receive_time:.2f} seconds"
            )
            print(result_text)  # Ensure this prints to console for debugging
            App.get_running_app().update_terminal(result_text)  # Update terminal through app instance

class BLEScannerApp(App):
    previous_data = None  # Store the previous data for comparison

    def build(self):
        self.client = None
        self.loop = asyncio.get_event_loop()
        self.layout = BoxLayout(orientation='vertical')
        self.speed_test_instance = SpeedTest()  # Initialize the speed test module
        self.is_speed_testing = False  # Flag to indicate if speed test is running
        
        self.tab_panel = TabbedPanel(do_default_tab=False)
        
        # Terminal Tab
        self.terminal_tab = TabbedPanelItem(text='Terminal')
        terminal_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        self.terminal = TextInput(size_hint_y=None, height=300, readonly=True)
        terminal_layout.add_widget(self.terminal)
        
        send_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.message_input = TextInput(size_hint_x=0.8, multiline=False)
        send_layout.add_widget(self.message_input)
        
        send_button = Button(text='Send', size_hint_x=0.2)
        send_button.bind(on_press=self.send_message)
        send_layout.add_widget(send_button)
        
        speed_test_button = Button(text='Speed Test', size_hint_x=0.2)
        speed_test_button.bind(on_press=self.speed_test)
        send_layout.add_widget(speed_test_button)
        
        terminal_layout.add_widget(send_layout)
        self.terminal_tab.add_widget(terminal_layout)
        self.tab_panel.add_widget(self.terminal_tab)
        
        # Connection Tab
        self.connection_tab = TabbedPanelItem(text='Connection')
        connection_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        self.scan_button = Button(text='Scan for BLE Devices', size_hint_y=None, height=40)
        self.scan_button.bind(on_press=self.start_scan)
        connection_layout.add_widget(self.scan_button)
        
        self.device_scroll = ScrollView(size_hint=(1, 0.5))
        self.device_layout = GridLayout(cols=1, size_hint_y=None, spacing=10, padding=10)
        self.device_layout.bind(minimum_height=self.device_layout.setter('height'))
        self.device_scroll.add_widget(self.device_layout)
        connection_layout.add_widget(self.device_scroll)
        
        self.connect_button = Button(text='Connect to Selected Device', size_hint_y=None, height=40)
        self.connect_button.bind(on_press=self.connect_to_selected_device)
        connection_layout.add_widget(self.connect_button)
        
        self.connection_tab.add_widget(connection_layout)
        self.tab_panel.add_widget(self.connection_tab)
        
        self.layout.add_widget(self.tab_panel)
        
        return self.layout

    def start_scan(self, instance):
        self.device_layout.clear_widgets()
        threading.Thread(target=self.run_async_scan).start()

    def run_async_scan(self):
        asyncio.run(self.scan_ble_devices())

    @mainthread
    def add_device_button(self, device):
        if device.name is None:
            return
        button = ToggleButton(text=f"{device.name} ({device.address})", size_hint_y=None, height=40, group='devices')
        self.device_layout.add_widget(button)

    async def scan_ble_devices(self):
        try:
            devices = await BleakScanner.discover()
            for device in devices:
                self.add_device_button(device)
        except Exception as e:
            self.update_terminal(f"An error occurred: {str(e)}")

    def connect_to_selected_device(self, instance):
        selected_button = next((btn for btn in self.device_layout.children if isinstance(btn, ToggleButton) and btn.state == 'down'), None)
        if selected_button:
            address = selected_button.text.split('(')[-1][:-1]
            threading.Thread(target=self.run_async_connect, args=(address,)).start()

    def run_async_connect(self, address):
        asyncio.run(self.connect_and_listen(address))

    async def connect_and_listen(self, address):
        try:
            self.client = BleakClient(address)
            await self.client.connect()
            if self.client.is_connected:
                self.update_terminal(f"Connected to {address}")
                services = await self.client.get_services()
                self.read_char_uuid = None
                self.write_char_uuid = None
                for service in services:
                    for char in service.characteristics:
                        if 'read' in char.properties:
                            self.read_char_uuid = char.uuid
                        if 'write' in char.properties or 'write-without-response' in char.properties:
                            self.write_char_uuid = char.uuid
        except Exception as e:
            self.update_terminal(f"Error: {str(e)}")

    async def read_data(self, client):
        try:
            start_time = time.time()
            data = await client.read_gatt_char(self.read_char_uuid)
            end_time = time.time()
            return data, end_time - start_time
        except Exception as e:
            self.update_terminal(f"Read error: {str(e)}")
            return None, 0

    def send_message(self, instance):
        message = self.message_input.text
        if message:
            threading.Thread(target=self.run_async_send, args=(message,)).start()
            self.message_input.text = ''

    def run_async_send(self, message):
        asyncio.run(self.perform_send_message(message))

    async def perform_send_message(self, message):
        try:
            if self.client and self.client.is_connected:
                chunks = [message[i:i+MAX_PACKET_SIZE] for i in range(0, len(message), MAX_PACKET_SIZE)]
                for chunk in chunks:
                    await self.client.write_gatt_char(self.write_char_uuid, chunk.encode('utf-8'), response=True)
                    self.update_terminal(f"Sent: {chunk}")
                    response, receive_time = await self.read_data(self.client)
                    if response:
                        self.speed_test_instance.add_data_received(len(response), receive_time)
                        self.update_terminal(f"Received: {response.decode('utf-8')}")
        except Exception as e:
            self.update_terminal(f"Send error: {str(e)}")

    def speed_test(self, instance):
        if self.write_char_uuid and self.client and self.client.is_connected:
            threading.Thread(target=self.run_async_speed_test).start()
        else:
            self.update_terminal("No write characteristic selected or not connected to a device.")

    def run_async_speed_test(self):
        asyncio.run(self.perform_speed_test())

    async def perform_speed_test(self):
        self.is_speed_testing = True
        self.speed_test_instance.start()  # Start speed test
        self.update_terminal("Speed test in progress...")
        
        async def send_packet(client, write_char_uuid, read_char_uuid, data, speed_test_instance):
            try:
                speed_test_instance.start_sending()
                await client.write_gatt_char(write_char_uuid, data.encode('utf-8'), response=True)
                speed_test_instance.end_sending()
                speed_test_instance.add_data_sent(len(data))
                
                speed_test_instance.start_receiving()
                response, receive_time = await client.read_gatt_char(read_char_uuid)
                speed_test_instance.end_receiving()
                if response:
                    speed_test_instance.add_data_received(len(response), receive_time)
                    App.get_running_app().update_terminal(f"Received: {response.decode('utf-8')}")
            except Exception as e:
                print(f"Send error: {str(e)}")
        
        try:
            data = "A" * PACKET_SIZE  # 244 bytes of data
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                tasks = []
                for _ in range(NUM_PACKETS):
                    tasks.append(executor.submit(asyncio.run, send_packet(self.client, self.write_char_uuid, self.read_char_uuid, data, self.speed_test_instance)))
                for task in tasks:
                    task.result()
            self.speed_test_instance.last_packet_time = time.time()
            await asyncio.sleep(1)  # Allow for final data processing before stopping the test
            self.speed_test_instance.stop()  # Stop and show results after last packet
            self.is_speed_testing = False
        except Exception as e:
            self.update_terminal(f"Speed test error: {str(e)}")
    
    @mainthread
    def update_terminal(self, text):
        self.terminal.text += text + '\n'
        self.terminal.cursor = (0, len(self.terminal.text))

if __name__ == '__main__':
    BLEScannerApp().run()
