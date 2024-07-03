import asyncio
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import mainthread
from bleak import BleakScanner, BleakClient
import threading

class BLEScannerApp(App):

    def build(self):
        self.client = None
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

        test_button = Button(text='Test 1000 Messages', size_hint_x=0.2)
        test_button.bind(on_press=self.test_1000_messages)
        send_layout.add_widget(test_button)
        
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
            self.devices = await BleakScanner.discover()
            if self.devices:
                for device in self.devices:
                    self.add_device_button(device)
            else:
                self.update_terminal("No BLE devices found")
        except Exception as e:
            self.update_terminal(f"An error occurred: {str(e)}")

    def connect_to_selected_device(self, instance):
        selected_button = next((btn for btn in self.device_layout.children if isinstance(btn, ToggleButton) and btn.state == 'down'), None)
        if selected_button:
            selected_device_info = selected_button.text
            address = selected_device_info.split('(')[-1][:-1]
            selected_device = next((device for device in self.devices if device.address == address), None)
            if selected_device:
                self.update_terminal(f"Connecting to {selected_device.name} ({selected_device.address})...")
                threading.Thread(target=self.run_async_connect, args=(selected_device,)).start()

    def run_async_connect(self, device):
        asyncio.run(self.connect_and_listen(device))

    async def connect_and_listen(self, device):
        try:
            self.client = BleakClient(device.address)
            await self.client.connect()
            if self.client.is_connected:
                self.update_terminal(f"Connected to {device.name} ({device.address})")
                services = await self.client.get_services()
                self.read_char_uuid = None
                self.write_char_uuid = None

                for service in services:
                    for char in service.characteristics:
                        if 'read' in char.properties:
                            self.read_char_uuid = char.uuid
                        if 'write' in char.properties or 'write-without-response' in char.properties:
                            self.write_char_uuid = char.uuid
                        self.update_terminal(f"Characteristic {char.uuid} has properties {char.properties}")

                if self.read_char_uuid:
                    await self.read_data(self.client)
            else:
                self.update_terminal("Failed to connect to the device.")
        except Exception as e:
            self.update_terminal(f"Error: {str(e)}")

    async def read_data(self, client):
        try:
            while client.is_connected:
                data = await client.read_gatt_char(self.read_char_uuid)
                self.update_terminal(f"Received: {data.decode('utf-8')}")
                await asyncio.sleep(3)  # Adjust the interval as needed
        except Exception as e:
            self.update_terminal(f"Read error: {str(e)}")

    def send_message(self, instance):
        message = self.message_input.text
        if message:
            if self.write_char_uuid and self.client and self.client.is_connected:
                threading.Thread(target=self.run_async_send, args=(self.write_char_uuid, message)).start()
            else:
                self.update_terminal("No write characteristic selected or not connected to a device.")
            self.message_input.text = ''

    def run_async_send(self, char_uuid, message):
        asyncio.run(self.perform_send_message(char_uuid, message))

    async def perform_send_message(self, char_uuid, message):
        try:
            if self.client and self.client.is_connected:
                await self.client.write_gatt_char(char_uuid, message.encode('utf-8'))
                self.update_terminal(f"Sent: {message}")
            else:
                self.update_terminal("Not connected to a device.")
        except Exception as e:
            self.update_terminal(f"Send error: {str(e)}")

    def test_1000_messages(self, instance):
        if self.write_char_uuid and self.client and self.client.is_connected:
            threading.Thread(target=self.run_async_test_1000_messages).start()
        else:
            self.update_terminal("No write characteristic selected or not connected to a device.")

    def run_async_test_1000_messages(self):
        asyncio.run(self.perform_test_1000_messages())

    async def perform_test_1000_messages(self):
        try:
            start_time = time.time()
            for i in range(1000):
                await self.client.write_gatt_char(self.write_char_uuid, b'Test')  # Send a simple byte, adjust as needed
                await asyncio.sleep(0.01)  # Slight delay to not overwhelm the BLE device
            end_time = time.time()
            duration = end_time - start_time
            self.update_terminal(f"Sent 1000 messages in {duration * 1000:.2f} ms")
        except Exception as e:
            self.update_terminal(f"Test error: {str(e)}")

    @mainthread
    def update_terminal(self, text):
        self.terminal.text += text + '\n'
        self.terminal.cursor = (0, len(self.terminal.text))

if __name__ == '__main__':
    BLEScannerApp().run()