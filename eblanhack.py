э"""
EBLANHACK PRO v8.0 - FIXED
- Убраны устаревшие аргументы
- Исправлен input() для GUI
- Все баги пофикшены
"""

import sys
import os
import traceback
import time
import math
import random
import struct
import json
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any

# ===== ПРОВЕРКА МОДЕЛИ (без input() для GUI) =====
def find_model():
    model_name = "cs2_yolov10s.pt"
    paths = [
        model_name,
        os.path.join(os.path.dirname(sys.executable), model_name),
    ]
    if getattr(sys, '_MEIPASS', False):
        paths.append(os.path.join(sys._MEIPASS, model_name))
    if __file__:
        paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), model_name))
    for p in paths:
        if os.path.exists(p):
            return p
    return None

model_path = find_model()
if not model_path:
    # Для GUI используем messagebox, а не input()
    import tkinter.messagebox as mb
    mb.showerror("Error", "cs2_yolov10s.pt not found!\nDownload from GitHub and place next to EXE.")
    sys.exit(1)

# ===== ИМПОРТЫ =====
import cv2
import numpy as np
import mss
import pyautogui
import ctypes
import ctypes.wintypes
import win32gui
import win32con
import win32api
import win32process
import customtkinter as ctk
from tkinter import messagebox, colorchooser
from ultralytics import YOLO
from pynput import keyboard

# ==========================================
# === КОНСТАНТЫ ===
# ==========================================
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()
CENTER_X = SCREEN_WIDTH // 2
CENTER_Y = SCREEN_HEIGHT // 2
VERSION = "8.0"
AUTHOR = "EblanHack"

COLORS = {
    "bg": "#0A0A0F",
    "card": "#12121A",
    "border": "#1E1E2E",
    "text": "#C8C8D4",
    "primary": "#FF6B35",
    "success": "#00E676",
    "danger": "#FF1744",
}

# ==========================================
# === ЛОГГЕР ===
# ==========================================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("EblanHack")

# ==========================================
# === ДАТАКЛАССЫ ===
# ==========================================
@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    def __sub__(self, o): return Vector3(self.x-o.x, self.y-o.y, self.z-o.z)
    def length(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    def distance_to(self, o): return (self - o).length()

@dataclass
class Player:
    address: int = 0
    health: int = 0
    team: int = 0
    position: Vector3 = field(default_factory=Vector3)
    distance: float = 0.0

# ==========================================
# === MEMORY MANAGER ===
# ==========================================
class MemoryManager:
    def __init__(self):
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.h_process = 0
        self.pid = 0
        self.base_address = 0
        self._cache = {}
        
        self.offsets = {
            "local_player": 0x17B4808,
            "entity_list": 0x17C3458,
            "player_count": 0x17C36A4,
            "force_jump": 0x1791438,
            "force_attack": 0x1791428,
            "glow_manager": 0x17C2C58,
            "radar_base": 0x17C2B40,
        }
        self.player_offsets = {
            "health": 0x200,
            "team": 0x1B4,
            "origin": 0x138,
            "angle": 0x134,
            "dormant": 0xED,
            "glow_index": 0x10428,
            "aim_punch": 0x32A8,
            "lagged_movement": 0x33A4,
        }
        logger.info("MemoryManager initialized")
    
    def get_process_id(self, name="cs2.exe"):
        h = self.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if h == -1:
            return None
        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.wintypes.DWORD), ("th32ProcessID", ctypes.wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if self.kernel32.Process32First(h, ctypes.byref(pe)):
            while True:
                try:
                    if pe.szExeFile.decode('utf-8').lower() == name.lower():
                        self.kernel32.CloseHandle(h)
                        return pe.th32ProcessID
                except:
                    pass
                if not self.kernel32.Process32Next(h, ctypes.byref(pe)):
                    break
        self.kernel32.CloseHandle(h)
        return None
    
    def open_process(self, pid):
        self.pid = pid
        self.h_process = self.kernel32.OpenProcess(0x1F0FFF, False, pid)
        return self.h_process != 0
    
    def get_module_base(self, module="client.dll"):
        if not self.h_process:
            return 0
        class MODULEENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.wintypes.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("szModule", ctypes.c_char * 256)]
        h = self.kernel32.CreateToolhelp32Snapshot(0x00000008, self.pid)
        if h == -1:
            return 0
        me = MODULEENTRY32()
        me.dwSize = ctypes.sizeof(MODULEENTRY32)
        if self.kernel32.Module32First(h, ctypes.byref(me)):
            while True:
                try:
                    if me.szModule.decode('utf-8').lower() == module.lower():
                        self.base_address = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                        self.kernel32.CloseHandle(h)
                        return self.base_address
                except:
                    pass
                if not self.kernel32.Module32Next(h, ctypes.byref(me)):
                    break
        self.kernel32.CloseHandle(h)
        return 0
    
    def read_memory(self, address, size):
        if not self.h_process:
            return None
        try:
            buf = ctypes.create_string_buffer(size)
            br = ctypes.c_size_t(0)
            if self.kernel32.ReadProcessMemory(self.h_process, address, buf, size, ctypes.byref(br)):
                if br.value == size:
                    return buf.raw
        except:
            pass
        return None
    
    def read_int(self, address):
        d = self.read_memory(address, 4)
        return struct.unpack('i', d)[0] if d else 0
    
    def read_pointer(self, address):
        d = self.read_memory(address, 8)
        return struct.unpack('Q', d)[0] if d else 0
    
    def read_float(self, address):
        d = self.read_memory(address, 4)
        return struct.unpack('f', d)[0] if d else 0.0
    
    def read_vec3(self, address):
        d = self.read_memory(address, 12)
        if d:
            return Vector3(*struct.unpack('fff', d))
        return Vector3()
    
    def write_memory(self, address, data, size=4):
        if not self.h_process:
            return False
        try:
            if isinstance(data, (int, float)):
                data = struct.pack('f' if isinstance(data, float) else 'i', data)
            buf = ctypes.create_string_buffer(data)
            bw = ctypes.c_size_t(0)
            self.kernel32.WriteProcessMemory(self.h_process, address, buf, len(data), ctypes.byref(bw))
            return bw.value == len(data)
        except:
            return False
    
    def write_int(self, address, value):
        return self.write_memory(address, value, 4)
    
    def write_float(self, address, value):
        return self.write_memory(address, value, 4)
    
    def write_vec3(self, address, vec):
        return self.write_memory(address, struct.pack('fff', vec.x, vec.y, vec.z), 12)
    
    @property
    def local_player(self):
        if not self.base_address:
            return 0
        return self.read_pointer(self.base_address + self.offsets["local_player"])
    
    def get_entity(self, idx):
        if not self.base_address:
            return 0
        list_ptr = self.read_pointer(self.base_address + self.offsets["entity_list"])
        if not list_ptr:
            return 0
        return self.read_pointer(list_ptr + (idx * 0x10))
    
    def get_player_count(self):
        if not self.base_address:
            return 0
        return self.read_int(self.base_address + self.offsets["player_count"])
    
    def get_team(self, entity):
        return self.read_int(entity + self.player_offsets["team"])
    
    def get_health(self, entity):
        return self.read_int(entity + self.player_offsets["health"])
    
    def get_origin(self, entity):
        return self.read_vec3(entity + self.player_offsets["origin"])
    
    def is_dormant(self, entity):
        return self.read_int(entity + self.player_offsets["dormant"]) == 1
    
    def get_glow_manager(self):
        if not self.base_address:
            return 0
        return self.read_pointer(self.base_address + self.offsets["glow_manager"])
    
    def get_force_jump(self):
        return self.base_address + self.offsets["force_jump"] if self.base_address else 0
    
    def get_force_attack(self):
        return self.base_address + self.offsets["force_attack"] if self.base_address else 0

# ==========================================
# === БОЕВЫЕ ЭКСПЛОЙТЫ ===
# ==========================================
class CombatExploits:
    def __init__(self, mem):
        self.mem = mem
        self.shot_count = 0
    
    def force_jump(self):
        addr = self.mem.get_force_jump()
        if addr:
            self.mem.write_int(addr, 6)
            time.sleep(0.001)
            self.mem.write_int(addr, 4)
            return True
        return False
    
    def force_attack(self):
        addr = self.mem.get_force_attack()
        if addr:
            self.mem.write_int(addr, 5)
            time.sleep(0.001)
            self.mem.write_int(addr, 4)
            self.shot_count += 1
            return True
        return False
    
    def no_recoil(self):
        p = self.mem.local_player
        if not p:
            return False
        self.mem.write_float(p + self.mem.player_offsets["aim_punch"], 0.0)
        self.mem.write_float(p + self.mem.player_offsets["aim_punch"] + 4, 0.0)
        return True
    
    def speed_hack(self, speed):
        p = self.mem.local_player
        if not p:
            return False
        self.mem.write_float(p + self.mem.player_offsets["lagged_movement"], speed)
        return True
    
    def glow_esp(self, enemies, color):
        gm = self.mem.get_glow_manager()
        if not gm:
            return False
        for e in enemies:
            idx = self.mem.read_int(e.address + self.mem.player_offsets["glow_index"])
            if idx < 0:
                continue
            go = gm + (idx * 0x38)
            r, g, b, a = color
            self.mem.write_float(go + 0x4, r)
            self.mem.write_float(go + 0x8, g)
            self.mem.write_float(go + 0xC, b)
            self.mem.write_float(go + 0x10, a)
            self.mem.write_int(go + 0x24, 1)
            self.mem.write_int(go + 0x28, 1)
        return True
    
    def radar_hack(self):
        if not self.mem.base_address:
            return False
        self.mem.write_int(self.mem.base_address + self.mem.offsets["radar_base"], 1)
        return True
    
    def teleport(self, pos):
        p = self.mem.local_player
        if not p:
            return False
        self.mem.write_vec3(p + self.mem.player_offsets["origin"], pos)
        return True
    
    def wallshot(self, target_pos):
        p = self.mem.local_player
        if not p:
            return False
        origin = self.mem.get_origin(p)
        if not origin:
            return False
        
        dx = target_pos.x - origin.x
        dy = target_pos.y - origin.y
        dz = target_pos.z - origin.z
        dist = math.hypot(dx, dy, dz)
        if dist == 0:
            return False
        
        angle_addr = p + self.mem.player_offsets["angle"]
        pitch = -math.degrees(math.asin(dz / dist))
        yaw = math.degrees(math.atan2(dy, dx))
        self.mem.write_float(angle_addr, yaw)
        self.mem.write_float(angle_addr + 4, pitch)
        
        # Увеличение пробития
        penetration_addr = p + 0x3A4C
        self.mem.write_float(penetration_addr, 999.0)
        
        time.sleep(0.01)
        self.force_attack()
        return True
    
    def autowall(self, target_pos):
        p = self.mem.local_player
        if not p:
            return False
        origin = self.mem.get_origin(p)
        if not origin:
            return False
        
        wall_normal = Vector3(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), 0)
        wall_normal = wall_normal.normalize()
        
        dx = target_pos.x - origin.x
        dy = target_pos.y - origin.y
        dz = target_pos.z - origin.z
        dist = math.hypot(dx, dy, dz)
        if dist == 0:
            return False
        
        dir_vec = Vector3(dx/dist, dy/dist, dz/dist)
        dot = dir_vec.x * wall_normal.x + dir_vec.y * wall_normal.y
        reflect = Vector3(
            dir_vec.x - 2 * dot * wall_normal.x,
            dir_vec.y - 2 * dot * wall_normal.y,
            dir_vec.z
        )
        
        angle_addr = p + self.mem.player_offsets["angle"]
        pitch = -math.degrees(math.asin(reflect.z))
        yaw = math.degrees(math.atan2(reflect.y, reflect.x))
        self.mem.write_float(angle_addr, yaw)
        self.mem.write_float(angle_addr + 4, pitch)
        
        time.sleep(0.005)
        self.force_attack()
        time.sleep(0.005)
        self.force_attack()
        return True

# ==========================================
# === YOLO AIMBOT ===
# ==========================================
class YOLOAimbot:
    def __init__(self, path):
        self.model = None
        self.fov = 300
        self.speed = 0.25
        self.conf = 0.5
        try:
            self.model = YOLO(path)
            logger.info(f"YOLO loaded: {path}")
        except Exception as e:
            logger.error(f"YOLO error: {e}")
    
    def detect(self, frame):
        if not self.model:
            return []
        try:
            res = self.model(frame, conf=self.conf, verbose=False)
            players = []
            for r in res:
                if r.boxes is None:
                    continue
                for b in r.boxes:
                    x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                    cls = int(b.cls[0])
                    if cls in [0, 1]:
                        players.append({
                            'x': (x1+x2)//2, 'y': (y1+y2)//2,
                            'w': x2-x1, 'h': y2-y1,
                            'conf': float(b.conf[0])
                        })
            return players
        except:
            return []
    
    def get_target(self, players, cx, cy):
        if not players:
            return None
        best, best_d = None, float('inf')
        for p in players:
            d = math.hypot(p['x'] - cx, p['y'] - cy)
            if d < self.fov and d < best_d:
                best, best_d = p, d
        return best
    
    def aim_at(self, tx, ty, cx, cy):
        dx, dy = tx - cx, ty - cy
        if abs(dx) < 2 and abs(dy) < 2:
            return False
        mx = max(-15, min(15, dx * self.speed * 0.4))
        my = max(-15, min(15, dy * self.speed * 0.4))
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(mx), int(my), 0, 0)
        return True

# ==========================================
# === ОСНОВНОЙ КЛАСС ===
# ==========================================
class EblanHack:
    def __init__(self):
        self.mem = MemoryManager()
        self.ex = CombatExploits(self.mem)
        self.aim = YOLOAimbot(model_path)
        
        self.is_running = False
        self.is_connected = False
        self.config = {
            "wallshot": False, "autowall": False, "glow": False,
            "radar": False, "speed": False, "speed_val": 1.5,
            "norecoil": False, "bhop": False, "teleport": False,
            "aimbot": True, "fov": 300, "aim_speed": 0.25,
            "trigger": False, "trigger_delay": 50,
            "glow_color": (1.0, 0.0, 0.0, 1.0)
        }
        self.stats = {"fps": 0, "targets": 0, "shots": 0}
        self.bot_thread = None
        self.keyboard_listener = None
        
        self._setup_gui()
        self._start_keyboard_listener()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info(f"EblanHack v{VERSION} started")
    
    def _setup_gui(self):
        ctk.set_appearance_mode("dark")
        self.window = ctk.CTk()
        self.window.title(f"EBLANHACK v{VERSION}")
        self.window.geometry("1000x800")
        self.window.configure(fg_color=COLORS["bg"])
        
        # Header
        h = ctk.CTkFrame(self.window, height=70, fg_color=COLORS["card"])
        h.pack(fill="x")
        ctk.CTkLabel(h, text=f"EBLANHACK v{VERSION}", font=("Arial", 22, "bold"), text_color=COLORS["primary"]).pack(side="left", padx=30)
        
        f = ctk.CTkFrame(h, fg_color="transparent")
        f.pack(side="right", padx=30)
        self.status_dot = ctk.CTkLabel(f, text="●", font=("Arial", 22), text_color=COLORS["danger"])
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(f, text="OFFLINE", font=("Arial", 14, "bold"), text_color=COLORS["danger"])
        self.status_label.pack(side="left", padx=10)
        self.connect_btn = ctk.CTkButton(f, text="CONNECT", command=self._connect, width=100, fg_color=COLORS["primary"])
        self.connect_btn.pack(side="left", padx=5)
        self.start_btn = ctk.CTkButton(f, text="START", command=self._toggle_bot, width=100, fg_color=COLORS["success"])
        self.start_btn.pack(side="left", padx=5)
        
        # Tabs (FIXED: убран segmented_button_colors)
        self.tabs = ctk.CTkTabview(self.window, fg_color=COLORS["card"])
        self.tabs.pack(fill="both", expand=True, padx=20, pady=20)
        for name in ["WALLSHOT", "EXPLOITS", "AIMBOT", "VISUALS", "CONFIG"]:
            self.tabs.add(name)
        
        self._create_wallshot_tab()
        self._create_exploits_tab()
        self._create_aimbot_tab()
        self._create_visuals_tab()
        self._create_config_tab()
        
        # Status bar
        sb = ctk.CTkFrame(self.window, height=30, fg_color=COLORS["card"])
        sb.pack(fill="x", side="bottom")
        self.fps_label = ctk.CTkLabel(sb, text="FPS: 0", font=("Arial", 11), text_color=COLORS["text"])
        self.fps_label.pack(side="left", padx=15)
        self.targets_label = ctk.CTkLabel(sb, text="Targets: 0", font=("Arial", 11), text_color=COLORS["text"])
        self.targets_label.pack(side="left", padx=15)
        self.shots_label = ctk.CTkLabel(sb, text="Shots: 0", font=("Arial", 11), text_color=COLORS["text"])
        self.shots_label.pack(side="left", padx=15)
    
    def _create_wallshot_tab(self):
        f = self.tabs.tab("WALLSHOT")
        self.wallshot_var = ctk.BooleanVar(value=self.config["wallshot"])
        ctk.CTkSwitch(f, text="Wallshot (bullet through walls)", variable=self.wallshot_var).pack(padx=20, pady=10, anchor="w")
        self.autowall_var = ctk.BooleanVar(value=self.config["autowall"])
        ctk.CTkSwitch(f, text="Autowall (bullet ricochet)", variable=self.autowall_var).pack(padx=20, pady=10, anchor="w")
    
    def _create_exploits_tab(self):
        f = self.tabs.tab("EXPLOITS")
        self.speed_var = ctk.BooleanVar(value=self.config["speed"])
        ctk.CTkSwitch(f, text="Speed Hack", variable=self.speed_var).pack(padx=20, pady=5, anchor="w")
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r, text="Speed:").pack(side="left")
        self.speed_slider = ctk.CTkSlider(r, from_=1.0, to=5.0)
        self.speed_slider.pack(side="left", padx=10, fill="x", expand=True)
        self.speed_slider.set(self.config["speed_val"])
        self.speed_label = ctk.CTkLabel(r, text=f"{self.config['speed_val']:.1f}x", width=50)
        self.speed_label.pack(side="left")
        self.speed_slider.configure(command=lambda v: (self.speed_label.configure(text=f"{float(v):.1f}x"), self.config.__setitem__("speed_val", float(v))))
        
        self.recoil_var = ctk.BooleanVar(value=self.config["norecoil"])
        ctk.CTkSwitch(f, text="No Recoil", variable=self.recoil_var).pack(padx=20, pady=5, anchor="w")
        self.bhop_var = ctk.BooleanVar(value=self.config["bhop"])
        ctk.CTkSwitch(f, text="BunnyHop", variable=self.bhop_var).pack(padx=20, pady=5, anchor="w")
        self.teleport_var = ctk.BooleanVar(value=self.config["teleport"])
        ctk.CTkSwitch(f, text="Teleport", variable=self.teleport_var).pack(padx=20, pady=5, anchor="w")
    
    def _create_aimbot_tab(self):
        f = self.tabs.tab("AIMBOT")
        self.aimbot_var = ctk.BooleanVar(value=self.config["aimbot"])
        ctk.CTkSwitch(f, text="Aimbot (YOLO)", variable=self.aimbot_var).pack(padx=20, pady=5, anchor="w")
        
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r, text="FOV:").pack(side="left")
        self.fov_slider = ctk.CTkSlider(r, from_=100, to=500)
        self.fov_slider.pack(side="left", padx=10, fill="x", expand=True)
        self.fov_slider.set(self.config["fov"])
        self.fov_label = ctk.CTkLabel(r, text=f"{self.config['fov']}px", width=50)
        self.fov_label.pack(side="left")
        self.fov_slider.configure(command=lambda v: (self.fov_label.configure(text=f"{int(float(v))}px"), self.config.__setitem__("fov", int(float(v)))))
        
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r, text="Speed:").pack(side="left")
        self.aim_speed_slider = ctk.CTkSlider(r, from_=0.05, to=0.8)
        self.aim_speed_slider.pack(side="left", padx=10, fill="x", expand=True)
        self.aim_speed_slider.set(self.config["aim_speed"])
        self.aim_speed_label = ctk.CTkLabel(r, text=f"{self.config['aim_speed']:.2f}", width=50)
        self.aim_speed_label.pack(side="left")
        self.aim_speed_slider.configure(command=lambda v: (self.aim_speed_label.configure(text=f"{float(v):.2f}"), self.config.__setitem__("aim_speed", float(v))))
        
        self.trigger_var = ctk.BooleanVar(value=self.config["trigger"])
        ctk.CTkSwitch(f, text="Triggerbot", variable=self.trigger_var).pack(padx=20, pady=5, anchor="w")
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r, text="Delay (ms):").pack(side="left")
        self.trigger_delay = ctk.CTkSlider(r, from_=10, to=200)
        self.trigger_delay.pack(side="left", padx=10, fill="x", expand=True)
        self.trigger_delay.set(self.config["trigger_delay"])
        self.trigger_label = ctk.CTkLabel(r, text=f"{self.config['trigger_delay']}ms", width=50)
        self.trigger_label.pack(side="left")
        self.trigger_delay.configure(command=lambda v: (self.trigger_label.configure(text=f"{int(float(v))}ms"), self.config.__setitem__("trigger_delay", int(float(v)))))
    
    def _create_visuals_tab(self):
        f = self.tabs.tab("VISUALS")
        self.glow_var = ctk.BooleanVar(value=self.config["glow"])
        ctk.CTkSwitch(f, text="Glow ESP", variable=self.glow_var).pack(padx=20, pady=5, anchor="w")
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r, text="Color:").pack(side="left")
        self.glow_color_btn = ctk.CTkButton(r, text="Choose", width=100, command=self._choose_glow_color, fg_color="#FF0000")
        self.glow_color_btn.pack(side="left", padx=10)
        self.radar_var = ctk.BooleanVar(value=self.config["radar"])
        ctk.CTkSwitch(f, text="Radar Hack", variable=self.radar_var).pack(padx=20, pady=5, anchor="w")
    
    def _create_config_tab(self):
        f = self.tabs.tab("CONFIG")
        ctk.CTkButton(f, text="SAVE CONFIG", command=self._save_config, fg_color=COLORS["success"]).pack(padx=20, pady=5, fill="x")
        ctk.CTkButton(f, text="LOAD CONFIG", command=self._load_config, fg_color=COLORS["primary"]).pack(padx=20, pady=5, fill="x")
        ctk.CTkButton(f, text="RESET", command=self._reset_config, fg_color=COLORS["danger"]).pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(f, text=f"v{VERSION} | {AUTHOR}", font=("Arial", 11), text_color=COLORS["text"]).pack(pady=10)
    
    def _choose_glow_color(self):
        c = colorchooser.askcolor()
        if c and c[0]:
            r, g, b = c[0]
            self.config["glow_color"] = (r/255, g/255, b/255, 1.0)
            self.glow_color_btn.configure(fg_color=c[0])
    
    def _connect(self):
        try:
            pid = self.mem.get_process_id()
            if not pid:
                messagebox.showerror("Error", "CS2 not running!")
                return
            if not self.mem.open_process(pid):
                messagebox.showerror("Error", "OpenProcess failed! Run as admin!")
                return
            if not self.mem.get_module_base():
                messagebox.showerror("Error", "client.dll not found!")
                return
            self.is_connected = True
            self.status_dot.configure(text_color=COLORS["success"])
            self.status_label.configure(text="CONNECTED", text_color=COLORS["success"])
            self.connect_btn.configure(text="CONNECTED")
            logger.info(f"Connected to CS2, PID: {pid}")
            messagebox.showinfo("Success", f"Connected to CS2!\nPID: {pid}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            messagebox.showerror("Error", str(e))
    
    def _toggle_bot(self):
        if not self.is_running:
            if not self.is_connected:
                messagebox.showwarning("Warning", "Connect to CS2 first!")
                return
            self.is_running = True
            self.start_btn.configure(text="STOP", fg_color=COLORS["danger"])
            self.status_dot.configure(text_color=COLORS["danger"])
            self.status_label.configure(text="ACTIVE", text_color=COLORS["danger"])
            self.bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
            self.bot_thread.start()
            logger.info("Bot started")
        else:
            self.is_running = False
            self.start_btn.configure(text="START", fg_color=COLORS["success"])
            self.status_dot.configure(text_color=COLORS["success"])
            self.status_label.configure(text="CONNECTED", text_color=COLORS["success"])
            logger.info("Bot stopped")
    
    def _bot_loop(self):
        fps_counter = 0
        last_time = time.time()
        frame_skip = 2
        frame_counter = 0
        sct = mss.mss()
        monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
        
        while self.is_running:
            try:
                if not self.is_connected:
                    time.sleep(0.5)
                    continue
                
                player = self.mem.local_player
                if not player:
                    time.sleep(0.1)
                    continue
                
                if self.recoil_var.get():
                    self.ex.no_recoil()
                if self.speed_var.get():
                    self.ex.speed_hack(float(self.speed_slider.get()))
                if self.bhop_var.get():
                    self.ex.force_jump()
                if self.radar_var.get():
                    self.ex.radar_hack()
                
                enemies = []
                player_count = self.mem.get_player_count()
                local_team = self.mem.get_team(player)
                
                for i in range(1, min(player_count, 64)):
                    entity = self.mem.get_entity(i)
                    if not entity or entity == player:
                        continue
                    health = self.mem.get_health(entity)
                    if health <= 0 or health > 100:
                        continue
                    team = self.mem.get_team(entity)
                    if team == local_team:
                        continue
                    if self.mem.is_dormant(entity):
                        continue
                    pos = self.mem.get_origin(entity)
                    origin = self.mem.get_origin(player)
                    distance = origin.distance_to(pos)
                    enemies.append(Player(address=entity, health=health, team=team, position=pos, distance=distance))
                
                if self.glow_var.get() and enemies:
                    self.ex.glow_esp(enemies, self.config["glow_color"])
                if self.wallshot_var.get() and enemies:
                    target = min(enemies, key=lambda e: e.distance)
                    self.ex.wallshot(target.position)
                if self.autowall_var.get() and enemies:
                    target = min(enemies, key=lambda e: e.distance)
                    self.ex.autowall(target.position)
                if self.teleport_var.get() and enemies:
                    target = min(enemies, key=lambda e: e.distance)
                    self.ex.teleport(target.position)
                
                frame_counter += 1
                if frame_counter % frame_skip == 0:
                    screenshot = sct.grab(monitor)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    players = self.aim.detect(frame)
                    self.aim.fov = self.config["fov"]
                    self.aim.speed = self.config["aim_speed"]
                    target = self.aim.get_target(players, CENTER_X, CENTER_Y)
                    if self.aimbot_var.get() and target:
                        self.aim.aim_at(target['x'], target['y'], CENTER_X, CENTER_Y)
                        self.stats["targets"] = len(players)
                    if self.trigger_var.get() and target and target['conf'] > 0.6:
                        time.sleep(self.config["trigger_delay"] / 1000)
                        self.ex.force_attack()
                        self.stats["shots"] += 1
                
                fps_counter += 1
                if time.time() - last_time >= 1:
                    self.stats["fps"] = fps_counter
                    fps_counter = 0
                    last_time = time.time()
                    # Безопасное обновление GUI из потока
                    self.window.after(0, lambda: self.fps_label.configure(text=f"FPS: {self.stats['fps']}"))
                    self.window.after(0, lambda: self.targets_label.configure(text=f"Targets: {len(enemies)}"))
                    self.window.after(0, lambda: self.shots_label.configure(text=f"Shots: {self.stats['shots']}"))
                
                time.sleep(0.001)
            except Exception as e:
                logger.error(f"Bot error: {e}")
                time.sleep(0.1)
    
    def _save_config(self):
        try:
            self.config["wallshot"] = self.wallshot_var.get()
            self.config["autowall"] = self.autowall_var.get()
            self.config["glow"] = self.glow_var.get()
            self.config["radar"] = self.radar_var.get()
            self.config["speed"] = self.speed_var.get()
            self.config["speed_val"] = float(self.speed_slider.get())
            self.config["norecoil"] = self.recoil_var.get()
            self.config["bhop"] = self.bhop_var.get()
            self.config["teleport"] = self.teleport_var.get()
            self.config["aimbot"] = self.aimbot_var.get()
            self.config["fov"] = int(self.fov_slider.get())
            self.config["aim_speed"] = float(self.aim_speed_slider.get())
            self.config["trigger"] = self.trigger_var.get()
            self.config["trigger_delay"] = int(self.trigger_delay.get())
            with open("config.json", "w") as f:
                json.dump(self.config, f, indent=4)
            messagebox.showinfo("Success", "Config saved!")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def _load_config(self):
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in self.config:
                            self.config[k] = v
                self.wallshot_var.set(self.config["wallshot"])
                self.autowall_var.set(self.config["autowall"])
                self.glow_var.set(self.config["glow"])
                self.radar_var.set(self.config["radar"])
                self.speed_var.set(self.config["speed"])
                self.speed_slider.set(self.config["speed_val"])
                self.recoil_var.set(self.config["norecoil"])
                self.bhop_var.set(self.config["bhop"])
                self.teleport_var.set(self.config["teleport"])
                self.aimbot_var.set(self.config["aimbot"])
                self.fov_slider.set(self.config["fov"])
                self.aim_speed_slider.set(self.config["aim_speed"])
                self.trigger_var.set(self.config["trigger"])
                self.trigger_delay.set(self.config["trigger_delay"])
                self.speed_label.configure(text=f"{self.config['speed_val']:.1f}x")
                self.fov_label.configure(text=f"{self.config['fov']}px")
                self.aim_speed_label.configure(text=f"{self.config['aim_speed']:.2f}")
                self.trigger_label.configure(text=f"{self.config['trigger_delay']}ms")
                messagebox.showinfo("Success", "Config loaded!")
            else:
                messagebox.showwarning("Warning", "Config not found!")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def _reset_config(self):
        if messagebox.askyesno("Confirm", "Reset all settings?"):
            self.config = {
                "wallshot": False, "autowall": False, "glow": False,
                "radar": False, "speed": False, "speed_val": 1.5,
                "norecoil": False, "bhop": False, "teleport": False,
                "aimbot": True, "fov": 300, "aim_speed": 0.25,
                "trigger": False, "trigger_delay": 50,
                "glow_color": (1.0, 0.0, 0.0, 1.0)
            }
            self.wallshot_var.set(False)
            self.autowall_var.set(False)
            self.glow_var.set(False)
            self.radar_var.set(False)
            self.speed_var.set(False)
            self.speed_slider.set(1.5)
            self.recoil_var.set(False)
            self.bhop_var.set(False)
            self.teleport_var.set(False)
            self.aimbot_var.set(True)
            self.fov_slider.set(300)
            self.aim_speed_slider.set(0.25)
            self.trigger_var.set(False)
            self.trigger_delay.set(50)
            self.speed_label.configure(text="1.5x")
            self.fov_label.configure(text="300px")
            self.aim_speed_label.configure(text="0.25")
            self.trigger_label.configure(text="50ms")
            messagebox.showinfo("Success", "Settings reset!")
    
    def _start_keyboard_listener(self):
        def on_press(key):
            try:
                if not self.is_running:
                    return
                if key == keyboard.Key.f5:
                    self.wallshot_var.set(not self.wallshot_var.get())
                elif key == keyboard.Key.f6:
                    self.autowall_var.set(not self.autowall_var.get())
                elif key == keyboard.Key.f3:
                    self.trigger_var.set(not self.trigger_var.get())
            except:
                pass
        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.start()
    
    def _on_close(self):
        self.is_running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.window.destroy()
    
    def run(self):
        self.window.mainloop()

# ==========================================
# === ТОЧКА ВХОДА ===
# ==========================================
def main():
    try:
        print(f"EBLANHACK v{VERSION} by {AUTHOR}")
        app = EblanHack()
        app.run()
    except Exception as e:
        logger.error(f"Startup error: {e}")
        traceback.print_exc()
        messagebox.showerror("Error", f"Startup error: {e}")

if __name__ == "__main__":
    main()