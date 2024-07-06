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
MAX_WORKERS = 200

class BLEScannerApp(App):
    previous_data = None  # Store the previous data for comparison

    def build(self):
        self.client = None
        self.loop = asyncio.get_event_loop()
        self.layout = BoxLayout(orientation='vertical')
        
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
                    start_time = time.time()
                    await self.client.write_gatt_char(self.write_char_uuid, chunk.encode('utf-8'), response=True)
                    self.update_terminal(f"Sent: {chunk}")
                    response, receive_time = await self.read_data(self.client)
                    end_time = time.time()
                    if response:
                        total_time = end_time - start_time
                        self.update_terminal(f"Received: {response.decode('utf-8')}")
                        self.update_terminal(f"Time for packet: {total_time:.2f} seconds")
        except Exception as e:
            self.update_terminal(f"Send error: {str(e)}")

    @mainthread
    def update_terminal(self, text):
        self.terminal.text += text + '\n'
        self.terminal.cursor = (0, len(self.terminal.text))

if __name__ == '__main__':
    BLEScannerApp().run()
