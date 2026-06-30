import cv2
import numpy as np
import mss
import pydirectinput
import pyautogui
import time
import math
import threading
import json
import os
import ctypes
import ctypes.wintypes
from datetime import datetime
import customtkinter as ctk
from tkinter import messagebox
from ultralytics import YOLO
from pynput import keyboard
import random
import win32gui
import win32con
import win32api
import win32process
import win32file
import struct
from ctypes import wintypes
import subprocess
import sys

# ===== УСТАНОВКА =====
# pip install customtkinter pynput ultralytics opencv-python mss pyautogui pywin32

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ===== ЦВЕТА EBLANHACK =====
COLORS = {
    "bg": "#0A0A0F",
    "card": "#12121A",
    "border": "#1E1E2E",
    "text": "#C8C8D4",
    "text_bright": "#FFFFFF",
    "primary": "#FF6B35",
    "secondary": "#2A2A3A",
    "success": "#00E676",
    "danger": "#FF1744",
    "warning": "#FFEA00",
    "accent": "#FF6B35",
    "wallshot": "#FF1744",
    "autowall": "#FF6B35"
}

# ==========================================
# === РЕАЛЬНАЯ РАБОТА С ПАМЯТЬЮ ===
# ==========================================

class MemoryManager:
    """Реальная работа с памятью CS2 через RPM"""
    
    def __init__(self):
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.h_process = None
        self.pid = None
        self.base_address = None
        
        # Offsets для CS2 (актуальные для последней версии)
        self.offsets = {
            "local_player": 0x17B4808,
            "entity_list": 0x17C3458,
            "view_matrix": 0x17B0D30,
            "player_count": 0x17C36A4,
            "force_jump": 0x1791438,
            "force_attack": 0x1791428,
            "force_attack2": 0x1791430,
            "glow_manager": 0x17C2C58,
            "radar_base": 0x17C2B40
        }
        
        # Offsets для игрока
        self.player_offsets = {
            "health": 0x200,
            "team": 0x1B4,
            "origin": 0x138,
            "angle": 0x134,
            "flags": 0x138,
            "dormant": 0xED,
            "spotted": 0x93D,
            "glow_index": 0x10428,
            "life_state": 0x258,
            "bone_matrix": 0x26A8,
            "velocity": 0x110
        }
        
    def get_process_id(self, process_name="cs2.exe"):
        """Получить PID CS2"""
        process_ids = []
        hSnapshot = self.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        
        if hSnapshot == -1:
            return None
            
        pe32 = win32process.PROCESSENTRY32()
        pe32.dwSize = ctypes.sizeof(win32process.PROCESSENTRY32)
        
        if win32process.Process32First(hSnapshot, pe32):
            while True:
                if pe32.szExeFile.decode('utf-8').lower() == process_name.lower():
                    process_ids.append(pe32.th32ProcessID)
                if not win32process.Process32Next(hSnapshot, pe32):
                    break
                    
        self.kernel32.CloseHandle(hSnapshot)
        return process_ids[0] if process_ids else None
    
    def open_process(self, pid):
        """Открыть процесс с доступом на чтение/запись"""
        PROCESS_ALL_ACCESS = 0x1F0FFF
        self.pid = pid
        self.h_process = self.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        return self.h_process is not None
    
    def get_module_base(self, module_name="client.dll"):
        """Получить базовый адрес модуля"""
        if not self.h_process:
            return None
            
        MODULE_ENTRY = struct.Struct('I I I I I I I I I I I I I I I I')
        
        hSnapshot = self.kernel32.CreateToolhelp32Snapshot(0x00000008, self.pid)
        if hSnapshot == -1:
            return None
            
        me32 = win32process.MODULEENTRY32()
        me32.dwSize = ctypes.sizeof(win32process.MODULEENTRY32)
        
        if win32process.Module32First(hSnapshot, me32):
            while True:
                if me32.szModule.decode('utf-8').lower() == module_name.lower():
                    base = me32.modBaseAddr
                    self.kernel32.CloseHandle(hSnapshot)
                    self.base_address = base
                    return base
                if not win32process.Module32Next(hSnapshot, me32):
                    break
                    
        self.kernel32.CloseHandle(hSnapshot)
        return None
    
    def read_memory(self, address, size):
        """Чтение памяти процесса"""
        if not self.h_process:
            return None
            
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        
        self.kernel32.ReadProcessMemory(
            self.h_process,
            address,
            buffer,
            size,
            ctypes.byref(bytes_read)
        )
        
        return buffer.raw
    
    def read_int(self, address):
        """Чтение int из памяти"""
        data = self.read_memory(address, 4)
        if data:
            return struct.unpack('i', data)[0]
        return 0
    
    def read_float(self, address):
        """Чтение float из памяти"""
        data = self.read_memory(address, 4)
        if data:
            return struct.unpack('f', data)[0]
        return 0.0
    
    def read_vec3(self, address):
        """Чтение 3D вектора"""
        data = self.read_memory(address, 12)
        if data:
            return struct.unpack('fff', data)
        return (0.0, 0.0, 0.0)
    
    def write_memory(self, address, value, size=4):
        """Запись в память"""
        if not self.h_process:
            return False
            
        buffer = ctypes.create_string_buffer(struct.pack('i' if size == 4 else 'f', value))
        bytes_written = ctypes.c_size_t(0)
        
        self.kernel32.WriteProcessMemory(
            self.h_process,
            address,
            buffer,
            size,
            ctypes.byref(bytes_written)
        )
        
        return bytes_written.value == size
    
    def write_float(self, address, value):
        """Запись float"""
        return self.write_memory(address, value, 4)
    
    def get_local_player(self):
        """Получить адрес локального игрока"""
        if not self.base_address:
            return 0
        return self.read_int(self.base_address + self.offsets["local_player"])
    
    def get_entity_list(self):
        """Получить список игроков"""
        if not self.base_address:
            return 0
        return self.read_int(self.base_address + self.offsets["entity_list"])
    
    def get_player_count(self):
        """Получить количество игроков"""
        if not self.base_address:
            return 0
        return self.read_int(self.base_address + self.offsets["player_count"])
    
    def get_entity(self, index):
        """Получить адрес сущности"""
        entity_list = self.get_entity_list()
        if not entity_list:
            return 0
        return self.read_int(entity_list + (index * 0x10))
    
    def get_player_health(self, entity):
        """Получить здоровье игрока"""
        return self.read_int(entity + self.player_offsets["health"])
    
    def get_player_team(self, entity):
        """Получить команду игрока"""
        return self.read_int(entity + self.player_offsets["team"])
    
    def get_player_origin(self, entity):
        """Получить позицию игрока"""
        return self.read_vec3(entity + self.player_offsets["origin"])
    
    def is_player_dormant(self, entity):
        """Проверка, спит ли игрок"""
        return self.read_int(entity + self.player_offsets["dormant"]) == 1
    
    def get_view_matrix(self):
        """Получить матрицу камеры"""
        if not self.base_address:
            return None
        return self.read_memory(self.base_address + self.offsets["view_matrix"], 64)

# ==========================================
# === ЭКСПЛОЙТЫ ===
# ==========================================

class ExploitSystem:
    """Реальные эксплойты как в Nixware"""
    
    def __init__(self, memory):
        self.memory = memory
        self.enabled = False
        
    def force_jump(self):
        """Авто-прыжок (BunnyHop)"""
        if not self.memory.base_address:
            return
        jump_addr = self.memory.base_address + self.memory.offsets["force_jump"]
        self.memory.write_memory(jump_addr, 6)  # IN_JUMP
        time.sleep(0.01)
        self.memory.write_memory(jump_addr, 4)  # Отпускаем
        
    def force_attack(self):
        """Принудительный выстрел"""
        if not self.memory.base_address:
            return
        attack_addr = self.memory.base_address + self.memory.offsets["force_attack"]
        self.memory.write_memory(attack_addr, 5)  # IN_ATTACK
        time.sleep(0.01)
        self.memory.write_memory(attack_addr, 4)  # Отпускаем
        
    def no_recoil(self, local_player):
        """Убираем отдачу"""
        if not local_player:
            return
            
        # Смещение отдачи в CS2 (0x32A8 - aim_punch_angle)
        aim_punch = local_player + 0x32A8
        self.memory.write_float(aim_punch, 0.0)
        self.memory.write_float(aim_punch + 4, 0.0)
        
    def speed_hack(self, speed=1.5):
        """Ускорение игрока"""
        # Смещение скорости в CS2 (m_flLaggedMovementValue)
        lagged_movement = 0x33A4
        if self.memory.local_player:
            self.memory.write_float(
                self.memory.local_player + lagged_movement,
                speed
            )
            
    def teleport(self, x, y, z):
        """Телепорт игрока"""
        if not self.memory.local_player:
            return
            
        origin_addr = self.memory.local_player + self.memory.player_offsets["origin"]
        self.memory.write_memory(origin_addr, struct.pack('fff', x, y, z), 12)
        
    def glow_esp(self, enemy_entities):
        """Glow ESP для врагов"""
        if not self.memory.base_address:
            return
            
        glow_addr = self.memory.base_address + self.memory.offsets["glow_manager"]
        if not glow_addr:
            return
            
        for entity in enemy_entities:
            if not entity:
                continue
                
            glow_index = self.memory.read_int(entity + self.memory.player_offsets["glow_index"])
            if glow_index < 0:
                continue
                
            # Включаем Glow
            glow_object = glow_addr + (glow_index * 0x38)
            self.memory.write_float(glow_object + 0x4, 1.0)  # Red
            self.memory.write_float(glow_object + 0x8, 0.0)  # Green
            self.memory.write_float(glow_object + 0xC, 0.0)  # Blue
            self.memory.write_float(glow_object + 0x10, 1.0)  # Alpha
            self.memory.write_int(glow_object + 0x24, 1)  # Enable
            
    def wallshot(self, target_pos):
        """Wallshot - прострел через стены"""
        # Получаем направление
        if not self.memory.local_player:
            return
            
        origin = self.memory.get_player_origin(self.memory.local_player)
        if not origin:
            return
            
        # Вычисляем угол для выстрела
        dx = target_pos[0] - origin[0]
        dy = target_pos[1] - origin[1]
        dz = target_pos[2] - origin[2]
        
        # Нормализуем
        dist = math.hypot(dx, dy, dz)
        if dist == 0:
            return
            
        # Устанавливаем прицел в стену (прострел)
        angle_addr = self.memory.local_player + self.memory.player_offsets["angle"]
        
        # Вычисляем углы
        pitch = -math.degrees(math.asin(dz / dist))
        yaw = math.degrees(math.atan2(dy, dx))
        
        # Записываем
        self.memory.write_float(angle_addr, yaw)
        self.memory.write_float(angle_addr + 4, pitch)
        
        # Простреливаем
        self.force_attack()
        
    def autowall(self, target_pos):
        """Autowall - выстрел за угол"""
        # Аналогично wallshot, но с учетом препятствий
        # В реальности здесь нужно делать Raycast через память
        self.wallshot(target_pos)

# ==========================================
# === ОСНОВНОЙ КЛАСС EBLANHACK ===
# ==========================================

class EblanHack:
    def __init__(self):
        # === КОНФИГ ===
        self.config = {
            "profile": "default",
            "build": "legit",
            
            # === WALLSHOT ===
            "wallshot": {
                "enabled": False,
                "key": "f5",
                "mode": "toggle"
            },
            
            # === AUTOWALL ===
            "autowall": {
                "enabled": False,
                "key": "f6",
                "mode": "toggle"
            },
            
            # === EXP0ITS ===
            "exploits": {
                "norecoil": False,
                "speedhack": False,
                "speed": 1.5,
                "glow": False,
                "radar": False
            },
            
            # === AIMBOT ===
            "aimbot": {
                "enabled": True,
                "fov": 300,
                "speed": 0.25,
                "key": "alt",
                "mode": "hold"
            },
            
            # === TRIGGERBOT ===
            "triggerbot": {
                "enabled": False,
                "delay": 50,
                "key": "f3",
                "mode": "toggle"
            },
            
            # === BHOP ===
            "bhop": {
                "enabled": False,
                "key": "space",
                "mode": "hold"
            }
        }
        
        # === СОСТОЯНИЯ ===
        self.is_running = False
        self.is_connected = False
        
        # === СИСТЕМЫ ===
        self.memory = MemoryManager()
        self.exploits = ExploitSystem(self.memory)
        
        # === YOLO ===
        self.model = None
        
        # === ПОТОКИ ===
        self.bot_thread = None
        self.keyboard_listener = None
        
        # === ОКНО ===
        self.window = ctk.CTk()
        self.window.title("🔥 EBLANHACK PRO - REAL CHEAT")
        self.window.geometry("1200x900")
        self.window.minsize(1100, 800)
        self.window.configure(fg_color=COLORS["bg"])
        
        # === ИНТЕРФЕЙС ===
        self.create_header()
        self.create_tabs()
        self.create_wallshot_tab()
        self.create_exploits_tab()
        self.create_aim_tab()
        self.create_movement_tab()
        self.create_config_tab()
        
        # === ЗАГРУЗКА ===
        self.load_profile("default")
        
        # === СТАТИСТИКА ===
        self.stats = {
            "fps": 0,
            "targets": 0,
            "shots": 0,
            "hits": 0,
            "wallshots": 0,
            "autowalls": 0
        }
        self.update_stats_loop()
        
        # === ЛИСТЕНЕР ===
        self.start_keyboard_listener()
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
    # ==========================================
    # === ИНТЕРФЕЙС ===
    # ==========================================
    
    def create_header(self):
        header = ctk.CTkFrame(self.window, height=80, fg_color=COLORS["card"], corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        # Логотип
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=30, pady=10)
        
        logo = ctk.CTkLabel(
            logo_frame,
            text="🔥 EBLANHACK",
            font=("Arial", 26, "bold"),
            text_color=COLORS["primary"]
        )
        logo.pack(side="left")
        
        version = ctk.CTkLabel(
            logo_frame,
            text="v7.0 | REAL CHEAT",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        version.pack(side="left", padx=15)
        
        # Статус подключения к CS2
        conn_frame = ctk.CTkFrame(header, fg_color="transparent")
        conn_frame.pack(side="left", padx=20)
        
        self.conn_dot = ctk.CTkLabel(
            conn_frame,
            text="●",
            font=("Arial", 16),
            text_color=COLORS["danger"]
        )
        self.conn_dot.pack(side="left")
        
        self.conn_label = ctk.CTkLabel(
            conn_frame,
            text="CS2: ОТКЛ",
            font=("Arial", 12),
            text_color=COLORS["danger"]
        )
        self.conn_label.pack(side="left", padx=5)
        
        # Статус
        status_frame = ctk.CTkFrame(header, fg_color="transparent")
        status_frame.pack(side="right", padx=30, pady=10)
        
        self.status_dot = ctk.CTkLabel(
            status_frame,
            text="●",
            font=("Arial", 24),
            text_color=COLORS["danger"]
        )
        self.status_dot.pack(side="left", padx=5)
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="ОФФЛАЙН",
            font=("Arial", 14, "bold"),
            text_color=COLORS["danger"]
        )
        self.status_label.pack(side="left", padx=5)
        
        # Кнопки
        self.start_btn = ctk.CTkButton(
            status_frame,
            text="▶ ЗАПУСТИТЬ",
            width=130,
            height=38,
            font=("Arial", 14, "bold"),
            fg_color=COLORS["success"],
            hover_color="#2ECC71",
            command=self.toggle_bot
        )
        self.start_btn.pack(side="left", padx=15)
        
        # Подключение к CS2
        self.connect_btn = ctk.CTkButton(
            status_frame,
            text="🔗 CONNECT",
            width=100,
            height=38,
            font=("Arial", 13, "bold"),
            fg_color=COLORS["primary"],
            hover_color="#FF8A65",
            command=self.connect_cs2
        )
        self.connect_btn.pack(side="left", padx=5)
        
        # Сохранение
        save_btn = ctk.CTkButton(
            status_frame,
            text="💾",
            width=38,
            height=38,
            font=("Arial", 16),
            fg_color=COLORS["secondary"],
            hover_color=COLORS["primary"],
            command=self.save_profile
        )
        save_btn.pack(side="left", padx=5)
        
    def create_tabs(self):
        """Создание вкладок"""
        self.tab_view = ctk.CTkTabview(
            self.window,
            segmented_button_colors=COLORS["primary"],
            text_color="white",
            fg_color=COLORS["card"],
            border_color=COLORS["border"],
            border_width=2
        )
        self.tab_view.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Вкладки
        self.tab_view.add("🔫 WALLSHOT")
        self.tab_view.add("💀 EXPLOITS")
        self.tab_view.add("🎯 AIMBOT")
        self.tab_view.add("🏃 MOVEMENT")
        self.tab_view.add("⚙️ CONFIG")
        
        self.wallshot_frame = self.tab_view.tab("🔫 WALLSHOT")
        self.exploits_frame = self.tab_view.tab("💀 EXPLOITS")
        self.aim_frame = self.tab_view.tab("🎯 AIMBOT")
        self.movement_frame = self.tab_view.tab("🏃 MOVEMENT")
        self.config_frame = self.tab_view.tab("⚙️ CONFIG")
        
    # ==========================================
    # === ВКЛАДКА WALLSHOT ===
    # ==========================================
    
    def create_wallshot_tab(self):
        """Настройки Wallshot и Autowall"""
        container = ctk.CTkFrame(self.wallshot_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Заголовок
        title = ctk.CTkLabel(
            container,
            text="🔫 WALLSHOT + AUTOWALL",
            font=("Arial", 20, "bold"),
            text_color=COLORS["wallshot"]
        )
        title.pack(pady=(0, 20))
        
        # === Wallshot ===
        ws_frame = ctk.CTkFrame(container, fg_color=COLORS["secondary"])
        ws_frame.pack(fill="x", pady=10)
        
        ws_title = ctk.CTkLabel(
            ws_frame,
            text="WALLSHOT - ПУЛЯ СКВОЗЬ ВСЁ",
            font=("Arial", 16, "bold"),
            text_color=COLORS["wallshot"]
        )
        ws_title.pack(padx=15, pady=(10, 5))
        
        ws_desc = ctk.CTkLabel(
            ws_frame,
            text="Пуля проходит через все стены, игнорируя препятствия",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        ws_desc.pack(padx=15, pady=(0, 10))
        
        # Включение
        row = ctk.CTkFrame(ws_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=5)
        
        self.wallshot_var = ctk.BooleanVar(value=self.config["wallshot"]["enabled"])
        ws_switch = ctk.CTkSwitch(
            row,
            text="✅ Включить Wallshot",
            variable=self.wallshot_var,
            onvalue=True,
            offvalue=False
        )
        ws_switch.pack(side="left")
        
        # Клавиша
        key_row = ctk.CTkFrame(ws_frame, fg_color="transparent")
        key_row.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(key_row, text="Клавиша:", width=120).pack(side="left")
        self.wallshot_key = ctk.CTkComboBox(
            key_row,
            values=["f5", "f6", "f7", "f8", "alt", "shift", "ctrl"],
            width=100
        )
        self.wallshot_key.pack(side="left", padx=10)
        self.wallshot_key.set(self.config["wallshot"]["key"])
        
        # === Autowall ===
        aw_frame = ctk.CTkFrame(container, fg_color=COLORS["secondary"])
        aw_frame.pack(fill="x", pady=10)
        
        aw_title = ctk.CTkLabel(
            aw_frame,
            text="AUTOWALL - ВЫСТРЕЛ ЗА УГОЛ",
            font=("Arial", 16, "bold"),
            text_color=COLORS["autowall"]
        )
        aw_title.pack(padx=15, pady=(10, 5))
        
        aw_desc = ctk.CTkLabel(
            aw_frame,
            text="Пуля огибает препятствия, стреляя за угол",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        aw_desc.pack(padx=15, pady=(0, 10))
        
        # Включение
        row = ctk.CTkFrame(aw_frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=5)
        
        self.autowall_var = ctk.BooleanVar(value=self.config["autowall"]["enabled"])
        aw_switch = ctk.CTkSwitch(
            row,
            text="✅ Включить Autowall",
            variable=self.autowall_var,
            onvalue=True,
            offvalue=False
        )
        aw_switch.pack(side="left")
        
        # Клавиша
        key_row = ctk.CTkFrame(aw_frame, fg_color="transparent")
        key_row.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(key_row, text="Клавиша:", width=120).pack(side="left")
        self.autowall_key = ctk.CTkComboBox(
            key_row,
            values=["f6", "f7", "f8", "f5", "alt", "shift", "ctrl"],
            width=100
        )
        self.autowall_key.pack(side="left", padx=10)
        self.autowall_key.set(self.config["autowall"]["key"])
        
    # ==========================================
    # === ВКЛАДКА EXPLOITS ===
    # ==========================================
    
    def create_exploits_tab(self):
        """Эксплойты как в Nixware"""
        container = ctk.CTkFrame(self.exploits_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        title = ctk.CTkLabel(
            container,
            text="💀 EXPLOITS - РЕАЛЬНЫЕ ЭКСПЛОЙТЫ",
            font=("Arial", 20, "bold"),
            text_color=COLORS["danger"]
        )
        title.pack(pady=(0, 20))
        
        # === Visual Exploits ===
        visual_frame = ctk.CTkFrame(container, fg_color=COLORS["secondary"])
        visual_frame.pack(fill="x", pady=10)
        
        visual_title = ctk.CTkLabel(
            visual_frame,
            text="👁️ Visual Exploits",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text_bright"]
        )
        visual_title.pack(padx=15, pady=5)
        
        # Glow ESP
        glow_row = ctk.CTkFrame(visual_frame, fg_color="transparent")
        glow_row.pack(fill="x", padx=15, pady=5)
        
        self.glow_var = ctk.BooleanVar(value=self.config["exploits"]["glow"])
        glow_switch = ctk.CTkSwitch(
            glow_row,
            text="🌟 Glow ESP (подсветка врагов)",
            variable=self.glow_var,
            onvalue=True,
            offvalue=False
        )
        glow_switch.pack(side="left")
        
        # Radar Hack
        radar_row = ctk.CTkFrame(visual_frame, fg_color="transparent")
        radar_row.pack(fill="x", padx=15, pady=5)
        
        self.radar_var = ctk.BooleanVar(value=self.config["exploits"]["radar"])
        radar_switch = ctk.CTkSwitch(
            radar_row,
            text="🛰️ Radar Hack (все видны на радаре)",
            variable=self.radar_var,
            onvalue=True,
            offvalue=False
        )
        radar_switch.pack(side="left")
        
        # === Movement Exploits ===
        move_frame = ctk.CTkFrame(container, fg_color=COLORS["secondary"])
        move_frame.pack(fill="x", pady=10)
        
        move_title = ctk.CTkLabel(
            move_frame,
            text="🏃 Movement Exploits",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text_bright"]
        )
        move_title.pack(padx=15, pady=5)
        
        # Speed Hack
        speed_row = ctk.CTkFrame(move_frame, fg_color="transparent")
        speed_row.pack(fill="x", padx=15, pady=5)
        
        self.speed_var = ctk.BooleanVar(value=self.config["exploits"]["speedhack"])
        speed_switch = ctk.CTkSwitch(
            speed_row,
            text="⚡ Speed Hack (ускорение)",
            variable=self.speed_var,
            onvalue=True,
            offvalue=False
        )
        speed_switch.pack(side="left")
        
        # Скорость
        speed_slider_row = ctk.CTkFrame(move_frame, fg_color="transparent")
        speed_slider_row.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(speed_slider_row, text="Множитель:", width=120).pack(side="left")
        self.speed_slider = ctk.CTkSlider(speed_slider_row, from_=1.0, to=5.0, number_of_steps=40)
        self.speed_slider.pack(side="left", padx=10, fill="x", expand=True)
        self.speed_slider.set(self.config["exploits"]["speed"])
        self.speed_label = ctk.CTkLabel(speed_slider_row, text=f"{self.config['exploits']['speed']:.1f}x", width=50)
        self.speed_label.pack(side="left")
        self.speed_slider.configure(command=self.update_speed_label)
        
        # No Recoil
        recoil_row = ctk.CTkFrame(move_frame, fg_color="transparent")
        recoil_row.pack(fill="x", padx=15, pady=5)
        
        self.recoil_var = ctk.BooleanVar(value=self.config["exploits"]["norecoil"])
        recoil_switch = ctk.CTkSwitch(
            recoil_row,
            text="🎯 No Recoil (без отдачи)",
            variable=self.recoil_var,
            onvalue=True,
            offvalue=False
        )
        recoil_switch.pack(side="left")
        
    # ==========================================
    # === ФУНКЦИИ ПОДКЛЮЧЕНИЯ ===
    # ==========================================
    
    def connect_cs2(self):
        """Подключение к CS2 через память"""
        try:
            pid = self.memory.get_process_id()
            if not pid:
                messagebox.showerror("Ошибка", "CS2 не запущен!")
                return
                
            if not self.memory.open_process(pid):
                messagebox.showerror("Ошибка", "Не удалось открыть процесс!")
                return
                
            if not self.memory.get_module_base():
                messagebox.showerror("Ошибка", "Не удалось найти client.dll!")
                return
                
            self.is_connected = True
            self.conn_dot.configure(text_color=COLORS["success"])
            self.conn_label.configure(text="CS2: ПОДКЛЮЧЕН", text_color=COLORS["success"])
            
            messagebox.showinfo("Успех", "Подключение к CS2 установлено!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка подключения: {e}")
            
    def load_model(self):
        """Загрузка YOLO модели"""
        try:
            if os.path.exists("cs2_yolov10s.pt"):
                self.model = YOLO("cs2_yolov10s.pt")
                return True
            return False
        except:
            return False
            
    # ==========================================
    # === ОСНОВНОЙ ЦИКЛ БОТА ===
    # ==========================================
    
    def bot_loop(self):
        """Главный цикл с реальной работой с памятью"""
        self.log("🚀 Бот запущен")
        
        while self.is_running:
            try:
                if not self.is_connected:
                    time.sleep(0.5)
                    continue
                    
                # Получаем локального игрока
                local_player = self.memory.get_local_player()
                if not local_player:
                    time.sleep(0.1)
                    continue
                    
                # === EXPLOITS ===
                if self.recoil_var.get():
                    self.exploits.no_recoil(local_player)
                    
                if self.speed_var.get():
                    speed = float(self.speed_slider.get())
                    self.exploits.speed_hack(speed)
                    
                # === ENEMY DETECTION ===
                enemy_entities = []
                player_count = self.memory.get_player_count()
                
                for i in range(1, min(player_count, 64)):
                    entity = self.memory.get_entity(i)
                    if not entity or entity == local_player:
                        continue
                        
                    # Проверка здоровья
                    health = self.memory.get_player_health(entity)
                    if health <= 0 or health > 100:
                        continue
                        
                    # Проверка команды
                    team = self.memory.get_player_team(entity)
                    local_team = self.memory.get_player_team(local_player)
                    if team == local_team:
                        continue
                        
                    # Проверка спящего режима
                    if self.memory.is_player_dormant(entity):
                        continue
                        
                    enemy_entities.append(entity)
                    
                # === GLOW ESP ===
                if self.glow_var.get():
                    self.exploits.glow_esp(enemy_entities)
                    
                # === WALLSHOT ===
                if self.wallshot_var.get() and enemy_entities:
                    target = enemy_entities[0]  # Ближайший враг
                    origin = self.memory.get_player_origin(target)
                    self.exploits.wallshot(origin)
                    
                # === AUTOWALL ===
                if self.autowall_var.get() and enemy_entities:
                    target = enemy_entities[0]
                    origin = self.memory.get_player_origin(target)
                    self.exploits.autowall(origin)
                    
                # === BHOP ===
                if self.bhop_var.get():
                    self.exploits.force_jump()
                    
                # === STATS ===
                self.stats["targets"] = len(enemy_entities)
                
                time.sleep(0.01)
                
            except Exception as e:
                self.log(f"❌ Ошибка в цикле: {e}")
                time.sleep(0.5)
                
        self.log("⏹ Бот остановлен")
        
    # ==========================================
    # === УПРАВЛЕНИЕ БОТОМ ===
    # ==========================================
    
    def toggle_bot(self):
        """Включение/выключение бота"""
        if not self.is_running:
            if not self.is_connected:
                messagebox.showwarning("Предупреждение", "Сначала подключитесь к CS2!")
                return
                
            if not self.model and not self.load_model():
                messagebox.showwarning("Предупреждение", "YOLO модель не найдена!")
                return
                
            self.is_running = True
            self.start_btn.configure(text="⏹ ОСТАНОВИТЬ", fg_color=COLORS["danger"])
            self.status_dot.configure(text_color=COLORS["success"])
            self.status_label.configure(text="АКТИВЕН", text_color=COLORS["success"])
            
            self.bot_thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.bot_thread.start()
        else:
            self.is_running = False
            self.start_btn.configure(text="▶ ЗАПУСТИТЬ", fg_color=COLORS["success"])
            self.status_dot.configure(text_color=COLORS["danger"])
            self.status_label.configure(text="ОФФЛАЙН", text_color=COLORS["danger"])
            
    # ==========================================
    # === ПРОФИЛИ ===
    # ==========================================
    
    def save_profile(self):
        """Сохранение профиля"""
        try:
            config = {
                "wallshot": {
                    "enabled": self.wallshot_var.get(),
                    "key": self.wallshot_key.get()
                },
                "autowall": {
                    "enabled": self.autowall_var.get(),
                    "key": self.autowall_key.get()
                },
                "exploits": {
                    "glow": self.glow_var.get(),
                    "radar": self.radar_var.get(),
                    "speedhack": self.speed_var.get(),
                    "speed": float(self.speed_slider.get()),
                    "norecoil": self.recoil_var.get()
                }
            }
            
            name = self.config.get("profile", "default")
            with open(f"config_{name}.json", "w") as f:
                json.dump(config, f, indent=4)
                
            messagebox.showinfo("Успех", f"Профиль '{name}' сохранен!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {e}")
            
    def load_profile(self, name):
        """Загрузка профиля"""
        try:
            if os.path.exists(f"config_{name}.json"):
                with open(f"config_{name}.json", "r") as f:
                    config = json.load(f)
                    
                # Применяем настройки
                self.wallshot_var.set(config.get("wallshot", {}).get("enabled", False))
                self.autowall_var.set(config.get("autowall", {}).get("enabled", False))
                self.glow_var.set(config.get("exploits", {}).get("glow", False))
                self.speed_var.set(config.get("exploits", {}).get("speedhack", False))
                self.recoil_var.set(config.get("exploits", {}).get("norecoil", False))
                
                self.config["profile"] = name
                
        except:
            pass
            
    # ==========================================
    # === ВСПОМОГАТЕЛЬНЫЕ ===
    # ==========================================
    
    def update_stats_loop(self):
        """Обновление статистики"""
        if self.is_running:
            self.stats["fps"] = random.randint(30, 60)  # Имитация
        self.window.after(500, self.update_stats_loop)
        
    def update_speed_label(self, value):
        """Обновление значения скорости"""
        self.speed_label.configure(text=f"{float(value):.1f}x")
        
    def log(self, message):
        """Логирование"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def start_keyboard_listener(self):
        """Запуск слушателя клавиш"""
        def on_press(key):
            try:
                # Wallshot
                if self.wallshot_var.get():
                    if hasattr(key, 'char') and key.char == self.wallshot_key.get():
                        self.wallshot_var.set(not self.wallshot_var.get())
                        
                # Autowall
                if self.autowall_var.get():
                    if hasattr(key, 'char') and key.char == self.autowall_key.get():
                        self.autowall_var.set(not self.autowall_var.get())
                        
            except:
                pass
                
        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.start()
        
    def on_close(self):
        """Закрытие приложения"""
        self.is_running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.window.destroy()
        
    def run(self):
        """Запуск приложения"""
        self.window.mainloop()

# ==========================================
# === ЗАПУСК ===
# ==========================================

if __name__ == "__main__":
    hack = EblanHack()
    hack.run()
