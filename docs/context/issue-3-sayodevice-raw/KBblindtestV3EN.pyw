import hid
import tkinter as tk
from tkinter import ttk, messagebox
import struct
import time
import random
from typing import Optional, Tuple, Dict, List, Protocol
from enum import Enum


SAYO_VID = 0x8089
SAYO_PID = 0x0009
SAYO_ECHO = 3

SAYO_SPEED_TO_HZ = {0: 1000, 1: 8000, 2: 4000, 3: 2000}
SAYO_HZ_TO_SPEED = {v: k for k, v in SAYO_SPEED_TO_HZ.items()}

SAYO_MODE_A = [1000, 8000]
SAYO_MODE_B = [1000, 2000, 4000, 8000]


SPARK_VID = 0x1CA6
SPARK_PACKET_SIZE = 64
SPARK_USAGE_PAGE = 0xFFB0


SPARK_HZ_COMMANDS = {
    1000: bytes([0x00, 0x02, 0x05, 0x02, 0x03]),
    2000: bytes([0x00, 0x02, 0x05, 0x02, 0x02]),
    4000: bytes([0x00, 0x02, 0x05, 0x02, 0x01]),
    8000: bytes([0x00, 0x02, 0x05, 0x02]),
}
SPARK_READ_COMMAND = bytes([0x00, 0x02, 0x05, 0x01])


SPARK_MODE_A = [1000, 8000]
SPARK_MODE_B = [1000, 2000, 4000, 8000]



class KeyboardType(Enum):
    SAYO_DEVICE = "SayoDevice"
    SPARKLINK = "SparkLink"


class KeyboardConfig:
    def __init__(
        self,
        keyboard_type: KeyboardType,
        vid: int,
        pid: Optional[int] = None,
        usage_page: Optional[int] = None,
        packet_size: int = 64,
        supports_multisampling: bool = False,
        polling_rates: Optional[List[int]] = None
    ):
        self.keyboard_type = keyboard_type
        self.vid = vid
        self.pid = pid
        self.usage_page = usage_page
        self.packet_size = packet_size
        self.supports_multisampling = supports_multisampling
        self.polling_rates = polling_rates or []


class KeyboardHandler(Protocol):
    
    def connect(self) -> None:
        ...
    
    def disconnect(self) -> None:
        ...
    
    def set_polling_rate(self, hz: int) -> None:
        ...
    
    def get_polling_rate(self) -> int:
        ...
    
    def set_multisampling(self, value: int) -> None:
        ...
    
    def get_multisampling(self) -> int:
        ...

    def get_max_multisampling(self) -> int:
        ...

    def reboot(self) -> None:
        ...


class SayoDeviceHandler:

    def __init__(self):
        self.device: Optional[hid.device] = None
        self.interface: Optional[Dict] = None
        self._max_multisampling: int = 79
    
    def connect(self) -> None:
        self.interface = self._find_keyboard_interface()
        self.device = hid.device()
        self.device.open_path(self.interface['path'])
    
    def disconnect(self) -> None:
        if self.device:
            self.device.close()
            self.device = None
    
    def _find_keyboard_interface(self) -> dict:
        devices = hid.enumerate(SAYO_VID, SAYO_PID)
        
        candidate_ff12 = None
        candidate_ff11 = None
        
        for dev in devices:
            up = dev.get('usage_page', 0)
            if up == 0xFF12 and candidate_ff12 is None:
                candidate_ff12 = dev
            elif up == 0xFF11 and candidate_ff11 is None:
                candidate_ff11 = dev
            if candidate_ff12 is not None and candidate_ff11 is not None:
                break
        
        if candidate_ff12 is not None:
            return {
                'path': candidate_ff12['path'],
                'report_id': 0x22,
                'packet_size': 1024,
                'usage_page': 0xFF12
            }
        elif candidate_ff11 is not None:
            return {
                'path': candidate_ff11['path'],
                'report_id': 0x21,
                'packet_size': 64,
                'usage_page': 0xFF11
            }
        else:
            raise Exception("SayoDevice keyboard (VID=0x8089, PID=0x0009) not found.")
    
    def _build_hid_v2_packet(self, report_id: int, echo: int, cmds: List[Tuple[int, int, bytes]], packet_size: int) -> bytes:
        body = b""
        for cmd, index, data in cmds:
            length = len(data) + 4
            cmd_header = struct.pack("<HBB", length, cmd, index)
            cmd_body = cmd_header + data
            while len(cmd_body) % 4 != 0:
                cmd_body += b'\x00'
            body += cmd_body
        
        packet = bytearray([report_id, echo, 0, 0]) + body
        if len(packet) > packet_size:
            raise ValueError(f"Packet is too large: {len(packet)} > {packet_size}")
        packet += b'\x00' * (packet_size - len(packet))
        
        words = struct.unpack_from(f"<{len(packet)//2}H", packet)
        checksum = sum(words) & 0xFFFF
        packet[2:4] = struct.pack("<H", checksum)
        
        return bytes(packet)
    
    def _send_command(self, echo: int, cmd: int, index: int, data: bytes = b"") -> List[Tuple[int, int, bytes]]:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        packet = self._build_hid_v2_packet(
            self.interface['report_id'],
            echo,
            [(cmd, index, data)],
            self.interface['packet_size']
        )
        self.device.write(packet)

        reply_raw = self.device.read(self.interface['packet_size'])
        if not reply_raw:
            raise Exception("Device did not respond")

        reply = bytes(reply_raw)
        if len(reply) < 4:
            raise Exception("Response too short")

        if reply[1] != echo:
            raise Exception(f"Echo mismatch: expected {echo}, got {reply[1]}")
        
        offset = 4
        responses = []
        while offset + 4 <= len(reply):
            length_status = struct.unpack_from("<H", reply, offset)[0]
            if length_status == 0:
                break
            length = length_status & 0x3FF
            status = (length_status >> 10) & 0x3F
            if status != 0:
                raise Exception(f"Device error: status {status:02X}")
            cmd_echo = reply[offset + 2]
            index_echo = reply[offset + 3]
            data_len = length - 4
            data_resp = reply[offset + 4: offset + 4 + data_len]
            responses.append((cmd_echo, index_echo, data_resp))
            offset += ((length + 3) // 4) * 4
        
        return responses
    
    def _read_config_data(self) -> bytearray:
        responses = self._send_command(SAYO_ECHO, 0x03, 0, b"")
        for cmd, idx, data in responses:
            if cmd == 0x03 and idx == 0 and len(data) >= 33:
                return bytearray(data)
        raise Exception("Failed to read configuration data")
    
    def _write_config_data(self, data: bytes) -> None:
        self._send_command(SAYO_ECHO, 0x03, 0, data)
    
    def get_polling_rate(self) -> int:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        data = self._read_config_data()
        if len(data) < 22:
            raise Exception("Not enough data to read polling rate")

        speed_code = data[22]
        hz = SAYO_SPEED_TO_HZ.get(speed_code)
        if hz is None:
            raise Exception(f"Unknown speed code: {speed_code}")
        return hz
    
    def set_polling_rate(self, hz: int) -> None:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        if hz not in SAYO_HZ_TO_SPEED:
            raise ValueError(f"Unsupported polling rate: {hz} Hz")
        
        data = self._read_config_data()
        data[22] = SAYO_HZ_TO_SPEED[hz]
        self._write_config_data(bytes(data))
        self.reboot()
    
    def get_multisampling(self) -> int:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        data = self._read_config_data()
        if len(data) < 33:
            raise Exception("Not enough data to read multisampling")
        return data[32]

    def get_max_multisampling(self) -> int:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        data = self._read_config_data()
        if len(data) < 34:
            raise Exception("Not enough data to read maximum multisampling")
        self._max_multisampling = data[33]
        return self._max_multisampling

    def set_multisampling(self, value: int) -> None:
        if not self.device or not self.interface:
            raise Exception("Device not connected")

        if not (0 <= value <= self._max_multisampling):
            raise ValueError(f"Multisampling value must be 0–{self._max_multisampling}")

        data = self._read_config_data()
        data[32] = value
        self._write_config_data(bytes(data))
    
    def reboot(self) -> None:
        if not self.device:
            raise Exception("Device not connected")


        devices = hid.enumerate(SAYO_VID, SAYO_PID)
        ff11_path = None
        for dev in devices:
            if dev.get('usage_page') == 0xFF11:
                ff11_path = dev['path']
                break

        if ff11_path is None:
            raise Exception("Management interface (Usage Page 0xFF11) not found")
        
        
        mgmt_device = hid.device()
        try:
            mgmt_device.open_path(ff11_path)
            
            
            save_data = struct.pack("<H", 0x7296)
            packet_save = self._build_hid_v2_packet(0x21, 18, [(0x0D, 0, save_data)], 64)
            mgmt_device.write(packet_save)
            
            time.sleep(0.1)
            
            
            reboot_data = struct.pack("<HBB", 0x7296, 0x01, 0xFE)
            packet_reboot = self._build_hid_v2_packet(0x21, 18, [(0x0E, 0, reboot_data)], 64)
            mgmt_device.write(packet_reboot)
            
        finally:
            mgmt_device.close()






class SparkLinkHandler:
    
    def __init__(self):
        self.device: Optional[hid.device] = None
        self.interface: Optional[Dict] = None
    
    def connect(self) -> None:
        self.interface = self._find_keyboard_interface()
        self.device = hid.device()
        self.device.open_path(self.interface['path'])
    
    def disconnect(self) -> None:
        if self.device:
            self.device.close()
            self.device = None
    
    def _find_keyboard_interface(self) -> dict:
        devices = hid.enumerate(SPARK_VID, 0)
        
        for dev in devices:
            up = dev.get('usage_page', 0)
            if up == SPARK_USAGE_PAGE:
                return {
                    'path': dev['path'],
                    'vid': dev['vendor_id'],
                    'pid': dev['product_id'],
                    'usage_page': SPARK_USAGE_PAGE
                }
        
        raise Exception(
            f"SparkLink keyboard (VID=0x{SPARK_VID:04X}, Usage Page=0x{SPARK_USAGE_PAGE:X}) not found.\n"
            "Make sure the keyboard is connected and in configuration mode."
        )
    
    def _send_command(self, command: bytes) -> bytes:
        if not self.device:
            raise Exception("Device not connected")


        packet = bytearray(command)
        while len(packet) < SPARK_PACKET_SIZE:
            packet.append(0x00)

        self.device.write(packet)

        response = self.device.read(SPARK_PACKET_SIZE)
        if not response:
            raise Exception("Device did not respond")

        return bytes(response)
    
    def get_polling_rate(self) -> int:
        response = self._send_command(SPARK_READ_COMMAND)



        if len(response) < 2:
            raise Exception("Response too short")

        rate_byte = response[3]


        rate_map = {0x03: 1000, 0x02: 2000, 0x01: 4000}
        hz = rate_map.get(rate_byte)


        if hz is None:
            hz = 8000

        return hz

    def set_polling_rate(self, hz: int) -> None:
        if hz not in SPARK_HZ_COMMANDS:
            raise ValueError(f"Unsupported polling rate: {hz} Hz. Supported: 1000, 2000, 4000, 8000 Hz")
        
        command = SPARK_HZ_COMMANDS[hz]
        self._send_command(command)
    
    def get_multisampling(self) -> int:
        raise NotImplementedError("SparkLink does not support multisampling")

    def get_max_multisampling(self) -> int:
        raise NotImplementedError("SparkLink does not support multisampling")

    def set_multisampling(self, value: int) -> None:
        raise NotImplementedError("SparkLink does not support multisampling")
    
    def reboot(self) -> None:
        pass






class KeyboardFactory:
    
    @staticmethod
    def get_handler(keyboard_type: KeyboardType) -> KeyboardHandler:
        if keyboard_type == KeyboardType.SAYO_DEVICE:
            return SayoDeviceHandler()
        elif keyboard_type == KeyboardType.SPARKLINK:
            return SparkLinkHandler()
        else:
            raise ValueError(f"Unknown keyboard type: {keyboard_type}")
    
    @staticmethod
    def get_config(keyboard_type: KeyboardType) -> KeyboardConfig:
        configs = {
            KeyboardType.SAYO_DEVICE: KeyboardConfig(
                keyboard_type=KeyboardType.SAYO_DEVICE,
                vid=SAYO_VID,
                pid=SAYO_PID,
                supports_multisampling=True,
                polling_rates=[1000, 2000, 4000, 8000]
            ),
            KeyboardType.SPARKLINK: KeyboardConfig(
                keyboard_type=KeyboardType.SPARKLINK,
                vid=SPARK_VID,
                usage_page=SPARK_USAGE_PAGE,
                packet_size=SPARK_PACKET_SIZE,
                supports_multisampling=False,
                polling_rates=[1000, 2000, 4000, 8000]
            )
        }
        return configs[keyboard_type]






def ms_from_multisampling(val: int) -> float:
    if val <= 0:
        return 0.0
    return 0.0625 * (val ** 0.8443)






class BlindTestApp:
    
    def __init__(self, root, keyboard_type: KeyboardType):
        self.root = root
        self.keyboard_type = keyboard_type
        self.keyboard: KeyboardHandler = KeyboardFactory.get_handler(keyboard_type)
        self.config = KeyboardFactory.get_config(keyboard_type)
        
        self.log: List[Tuple[int, Optional[int]]] = []
        self.test_type: Optional[str] = None
        self.options: List[int] = []
        self.option_labels: List[str] = []
        
        self._setup_window()
        self.create_test_type_selection()
    
    def _setup_window(self):
        keyboard_name = self.keyboard_type.value
        self.root.title(f"{keyboard_name} — Blind Test")
        self.root.geometry("520x420")

    def create_test_type_selection(self):
        self._clear_window()

        ttk.Label(self.root, text="Select test type", font=("Arial", 14)).pack(pady=30)


        ttk.Button(
            self.root,
            text="Polling Rate Test",
            command=lambda: self.select_test_type("polling")
        ).pack(pady=10)
        

        if self.config.supports_multisampling:
            ttk.Button(
                self.root,
                text="Latency Test (Multisampling)",
                command=lambda: self.select_test_type("multisampling")
            ).pack(pady=10)


        ttk.Button(
            self.root,
            text="Change Keyboard Type",
            command=self.change_keyboard_type
        ).pack(pady=20)
    
    def change_keyboard_type(self):
        self.root.destroy()
        create_keyboard_selection_window()
    
    def select_test_type(self, test_type: str):
        self.test_type = test_type
        if test_type == "polling":
            self.create_polling_setup_ui()
        elif test_type == "multisampling":
            self.create_multisampling_setup_ui()
    
    
    
    def create_polling_setup_ui(self):
        self._clear_window()

        ttk.Label(self.root, text="USB Polling Rate Blind Test", font=("Arial", 14)).pack(pady=15)


        self.mode_var = tk.StringVar(value="A")
        ttk.Radiobutton(
            self.root,
            text="Mode A: 1000 / 8000 Hz",
            variable=self.mode_var,
            value="A"
        ).pack(anchor=tk.W, padx=60, pady=5)
        ttk.Radiobutton(
            self.root,
            text="Mode B: 1000 / 2000 / 4000 / 8000 Hz",
            variable=self.mode_var,
            value="B"
        ).pack(anchor=tk.W, padx=60, pady=5)

        ttk.Label(
            self.root,
            text="Number of attempts (minimum 5):",
            font=("Arial", 10)
        ).pack(pady=(15, 5))
        self.attempts_var = tk.IntVar(value=5)
        attempts_spin = ttk.Spinbox(
            self.root,
            from_=5,
            to=30,
            textvariable=self.attempts_var,
            width=8
        )
        attempts_spin.pack()

        ttk.Button(self.root, text="Start Test", command=self.start_polling_test).pack(pady=20)
        ttk.Button(self.root, text="Back", command=self.create_test_type_selection).pack(pady=5)
    
    def start_polling_test(self):
        n = self.attempts_var.get()
        if n < 5:
            messagebox.showerror("Error", "Minimum 5 attempts!")
            return


        mode = self.mode_var.get()
        self.options = SPARK_MODE_A if mode == "A" else SPARK_MODE_B
        self.option_labels = [f"{hz} Hz" for hz in self.options]
        self.log = []


        try:
            self.keyboard.connect()
            self.keyboard.disconnect()
        except Exception as e:
            messagebox.showerror("Error", f"Keyboard not found:\n{e}")
            return

        self.run_trial(0, n)
    
    

    def create_multisampling_setup_ui(self):
        self._clear_window()

        ttk.Label(
            self.root,
            text="Latency Blind Test (Multisampling)",
            font=("Arial", 14)
        ).pack(pady=15)


        max_ms = 79
        try:
            self.keyboard.connect()
            max_ms = self.keyboard.get_max_multisampling()
            self.keyboard.disconnect()
        except Exception:
            pass

        self.ms_max_value = max_ms

        ttk.Label(
            self.root,
            text=f"Multisampling values (0–{max_ms}):",
            font=("Arial", 10)
        ).pack(pady=(10, 5))

        self.ms_val1 = tk.IntVar(value=10)
        self.ms_val2 = tk.IntVar(value=max_ms)

        frame = ttk.Frame(self.root)
        frame.pack(pady=5)
        ttk.Label(frame, text="Option 1:").grid(row=0, column=0, padx=5)
        ttk.Spinbox(frame, from_=0, to=max_ms, textvariable=self.ms_val1, width=5).grid(row=0, column=1, padx=5)
        ttk.Label(frame, text="Option 2:").grid(row=0, column=2, padx=5)
        ttk.Spinbox(frame, from_=0, to=max_ms, textvariable=self.ms_val2, width=5).grid(row=0, column=3, padx=5)

        ttk.Label(
            self.root,
            text="Number of attempts (minimum 5):",
            font=("Arial", 10)
        ).pack(pady=(15, 5))
        self.ms_attempts_var = tk.IntVar(value=5)
        attempts_spin = ttk.Spinbox(
            self.root,
            from_=5,
            to=30,
            textvariable=self.ms_attempts_var,
            width=8
        )
        attempts_spin.pack()

        ttk.Button(self.root, text="Start Test", command=self.start_multisampling_test).pack(pady=20)
        ttk.Button(self.root, text="Back", command=self.create_test_type_selection).pack(pady=5)
    
    def start_multisampling_test(self):
        val1 = self.ms_val1.get()
        val2 = self.ms_val2.get()
        n = self.ms_attempts_var.get()
        max_ms = self.ms_max_value

        if n < 5:
            messagebox.showerror("Error", "Minimum 5 attempts!")
            return
        if val1 == val2:
            messagebox.showerror("Error", "Values must be different!")
            return
        if not (0 <= val1 <= max_ms and 0 <= val2 <= max_ms):
            messagebox.showerror("Error", f"Values must be between 0 and {max_ms}!")
            return

        self.options = [val1, val2]
        self.option_labels = [
            f"{val1} (~{ms_from_multisampling(val1):.2f} ms)",
            f"{val2} (~{ms_from_multisampling(val2):.2f} ms)"
        ]
        self.log = []


        try:
            self.keyboard.connect()
            self.keyboard.disconnect()
        except Exception as e:
            messagebox.showerror("Error", f"Keyboard not found:\n{e}")
            return

        self.run_trial(0, n)
    
    
    
    def run_trial(self, trial: int, total: int):
        if trial >= total:
            self.show_results()
            return
        
        real_value = random.choice(self.options)
        
        try:
            self.keyboard.connect()
            
            if self.test_type == "polling":
                self._run_polling_trial(real_value)
            elif self.test_type == "multisampling":
                self._run_multisampling_trial(real_value)
            
        except Exception as e:
            messagebox.showerror(
                "Error applying setting",
                f"Failed to apply or confirm value:\n{e}\n\n"
                "Retrying..."
            )
            self.keyboard.disconnect()
            self.root.after(1000, lambda: self.run_trial(trial, total))
            return

        self.keyboard.disconnect()


        self._clear_window()

        ttk.Label(self.root, text=f"Attempt {trial + 1} of {total}", font=("Arial", 14)).pack(pady=20)
        if self.test_type == "polling":
            ttk.Label(self.root, text="What polling rate do you feel?").pack(pady=10)
        else:
            ttk.Label(self.root, text="What latency do you feel?").pack(pady=10)
        
        def on_choice(choice_value):
            self.log.append((real_value, choice_value))
            self.run_trial(trial + 1, total)
        
        for i, val in enumerate(self.options):
            label = self.option_labels[i]
            btn = ttk.Button(self.root, text=label, command=lambda v=val: on_choice(v))
            btn.pack(pady=5)

        ttk.Button(self.root, text="Skip", command=lambda: on_choice(None)).pack(pady=20)
        ttk.Button(self.root, text="End Test", command=self.abort_test).pack(pady=5)
    
    def _run_polling_trial(self, target_hz: int):
        self.keyboard.set_polling_rate(target_hz)


        if self.keyboard_type == KeyboardType.SAYO_DEVICE:
            time.sleep(5)
            self.keyboard.disconnect()
            self.keyboard.connect()

            confirmed_hz = self.keyboard.get_polling_rate()
            if confirmed_hz != target_hz:
                raise Exception(f"Expected {target_hz} Hz, but got {confirmed_hz} Hz")


        elif self.keyboard_type == KeyboardType.SPARKLINK:
            time.sleep(5)
            self.keyboard.disconnect()
            self.keyboard.connect()

            confirmed_hz = self.keyboard.get_polling_rate()
            if confirmed_hz != target_hz:
                raise Exception(f"Expected {target_hz} Hz, but got {confirmed_hz} Hz")

    def _run_multisampling_trial(self, target_value: int):
        self.keyboard.set_multisampling(target_value)


        confirmed_val = self.keyboard.get_multisampling()
        if confirmed_val != target_value:
            raise Exception(f"Expected multisampling={target_value}, got {confirmed_val}")
    
    def show_results(self):
        self._clear_window()

        title = "Test Results — " + (
            "Polling Rate" if self.test_type == "polling" else "Multisampling"
        )
        ttk.Label(self.root, text=title, font=("Arial", 16)).pack(pady=15)

        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        if not self.log:
            ttk.Label(
                frame,
                text="Test was aborted. No data to display.",
                font=("Arial", 11)
            ).pack(pady=20)
        else:
            tree = ttk.Treeview(
                frame,
                columns=("Trial", "Real", "Chosen"),
                show="headings",
                height=min(10, len(self.log))
            )
            tree.heading("Trial", text="Attempt")
            tree.heading("Real", text="Real Value")
            tree.heading("Chosen", text="User Choice")
            tree.column("Trial", width=80, anchor="center")
            tree.column("Real", width=180, anchor="center")
            tree.column("Chosen", width=180, anchor="center")
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscroll=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            correct = 0
            for i, (real, chosen) in enumerate(self.log, 1):
                if self.test_type == "polling":
                    real_str = f"{real} Hz"
                    chosen_str = f"{chosen} Hz" if chosen is not None else "—"
                else:
                    real_str = f"{real} (~{ms_from_multisampling(real):.2f} ms)"
                    chosen_str = f"{chosen} (~{ms_from_multisampling(chosen):.2f} ms)" if chosen is not None else "—"
                tree.insert("", "end", values=(i, real_str, chosen_str))
                if chosen == real:
                    correct += 1

            if self.log:
                accuracy = correct / len(self.log) * 100
                ttk.Label(
                    self.root,
                    text=f"Accuracy: {correct}/{len(self.log)} ({accuracy:.1f}%)",
                    font=("Arial", 12)
                ).pack(pady=10)

        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=15)
        ttk.Button(
            button_frame,
            text="Main Menu",
            command=self.create_test_type_selection
        ).pack()

    def abort_test(self):
        if messagebox.askyesno("End Test", "Are you sure you want to end the test?"):
            self.show_results()
    
    def _clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()






def create_keyboard_selection_window():
    root = tk.Tk()
    root.title("Keyboard Type Selection")
    root.geometry("400x300")

    def on_select(keyboard_type: KeyboardType):
        root.destroy()
        app_root = tk.Tk()
        app = BlindTestApp(app_root, keyboard_type)
        app_root.mainloop()

    ttk.Label(root, text="Select your keyboard type", font=("Arial", 14)).pack(pady=20)

    ttk.Button(
        root,
        text="SayoDevice",
        command=lambda: on_select(KeyboardType.SAYO_DEVICE),
        width=30
    ).pack(pady=10)

    ttk.Button(
        root,
        text="SparkLink",
        command=lambda: on_select(KeyboardType.SPARKLINK),
        width=30
    ).pack(pady=10)

    ttk.Label(
        root,
        text="SayoDevice: full test (polling rate + multisampling)\n"
             "SparkLink: polling rate test only",
        font=("Arial", 9),
        justify=tk.CENTER
    ).pack(pady=20)

    root.mainloop()






if __name__ == "__main__":
    create_keyboard_selection_window()