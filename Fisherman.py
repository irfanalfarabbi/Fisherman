import pyautogui,pyaudio,audioop,threading,time,win32api,configparser,mss,mss.tools,cv2,numpy
from dearpygui.core import *
from dearpygui.simple import *
import random

#Constants
IDLE = "IDLE" #Not doing anything
STARTING = "STARTING" #Bot is starting up and starting threads
STARTED = "STARTED" #Bot is started and threads are active
STOPPING = "STOPPING" #Bot is closing down and closing active threads
STOPPED = "STOPPED" #Bot is stopped and waiting
CASTING = "CASTING" #Casting out line to spot
CASTED = "CASTED" #Line is casted and waiting for fish
CATCHING = "CATCHING" #Bot is catching fish
CATCH_LIMIT = 600 #Suggested limit before fishing pole break

#Loads Settings
parser = configparser.ConfigParser()
parser.read('settings.ini')
debugmode = parser.getboolean('Settings','debug')
max_volume = parser.getint('Settings','Volume_Threshold')
screen_area = parser.get('Settings','tracking_zone')
detection_threshold = parser.getfloat('Settings','detection_threshold')
cast_timeout = parser.getint('Settings','cast_timeout')

screen_area = screen_area.strip('(')
screen_area = screen_area.strip(')')
cordies = screen_area.split(',')
screen_area = int(cordies[0]),int(cordies[1]),int(cordies[2]),int(cordies[3])

#screen_area = x1,y1,x2,y2
#Coords for fishing spots
fishing_coordinates = []

#extras, set window position
try:
    main_window_pos = parser.get('Settings','main_window_pos')
    main_window_pos = main_window_pos.strip('(')
    main_window_pos = main_window_pos.strip(')')
    main_window_pos = main_window_pos.split(',')
    main_window_pos_x = int(main_window_pos[0])
    main_window_pos_y = int(main_window_pos[1])
    set_main_window_pos(main_window_pos_x, main_window_pos_y)
except Exception as e:
    print(f"Error: {e}")

#select input device
p = pyaudio.PyAudio()
default_device = p.get_default_input_device_info()
input_device_index = default_device.get("index")
input_device_name = default_device.get("name")

try:
    device_count = p.get_host_api_info_by_index(0).get('deviceCount')
    for i in range(0, device_count):
        device = p.get_device_info_by_host_api_device_index(0, i)
        if (device.get("maxInputChannels")) > 0 and device.get("name").find("CABLE Output") == 0:
            input_device_index = device.get("index")
            input_device_name = device.get("name")
            break
except Exception as e:
    print(f"Notice: {e}")

#Sound Volume
total = 0

#Current Bot State
STATE = IDLE

#Thread Stopper
stop_button = True

#Stuff for mouse events
state_left = win32api.GetKeyState(0x01)
state_right = win32api.GetKeyState(0x02)

#fishing counters
casted_count = 0
heard_count = 0
hooked_count = 0
catched_count = 0

total_duration = 0
average_duration = 0
min_duration = 0
max_duration = 0
cast_time = 0
cast_power_min = 50
cast_power_max = 50

bait_counter = 0

food_timer = 0

##########################################################
#
#   These Functions handle bot state / minigame handling
#
##########################################################

#Scans the current input volume
def check_volume():
    global total,max_volume
    stream = p.open(format=pyaudio.paInt16,channels=2,rate=44100,input=True,input_device_index=input_device_index,frames_per_buffer=1024)
    current_section = 0
    while 1:
        if stop_button == False:
            total=0
            for i in range(0,2):
                data=stream.read(1024)
                if True:
                    reading=audioop.max(data, 2)
                    total=total+reading
                    if total > max_volume and STATE != CATCHING and STATE != CASTING:
                        do_catch()
        else:
            break

def get_new_spot():
    return random.choice(fishing_coordinates)

#Runs the casting function
def cast_hook():
    global STATE,cast_time,casted_count
    last_state = ""
    while 1:
        time.sleep(0.5)
        if STATE != last_state:
            print(f"Cast Hook Check! Stop: {stop_button}, State: {STATE}")
            last_state = STATE
        if stop_button == False:
            if STATE == CASTING or STATE == STARTED:
                time.sleep(1.5)
                pyautogui.mouseUp()
                x, y = get_new_spot()
                pyautogui.moveTo(x,y,tween=pyautogui.linear,duration=0.2)
                time.sleep(0.2)
                pyautogui.mouseDown()
                time.sleep(random.uniform(cast_power_min*9/1000, cast_power_max*9/1000))
                pyautogui.mouseUp()
                log_info(f"Casted towards: {x,y}", logger = "Information")
                casted_count += 1
                time.sleep(1.5)
                STATE = CASTED
                cast_time = time.time()
            elif STATE == CASTED:
                duration = time.time() - cast_time
                if duration > cast_timeout:
                    log_info(f"Waiting for too long: {cast_timeout} secs. Recasting", logger = "Information")
                    STATE = CASTING
                    pyautogui.mouseDown()
                    time.sleep(0.1)
                    pyautogui.mouseUp()
                    time.sleep(2)
        else:
            break

#Uses obj detection with OpenCV to find and track bobbers left / right coordinates
def do_catch():
    global STATE,heard_count,hooked_count,catched_count,bait_counter,cast_time,total_duration,average_duration,min_duration,max_duration
    if STATE != CASTING and STATE != STARTED:
        log_info(f"Hooked sound detected!", logger = "Information")
        heard_count += 1
        STATE = CATCHING
        pyautogui.mouseDown()
        pyautogui.mouseUp()
        duration = time.time() - cast_time
        #Initial scan. Waits for bobber to appear
        check = 0
        valid = False
        while check < 100:
            check += 1
            time.sleep(0.01)
            valid, location, size = detect_bobber()
            if valid: break
        if valid:
            log_info(f"Bobber detected after {round(check*0.1, 2)} secs. Starting to catch fish!", logger = "Information")
            hooked_count += 1
            bait_counter += 1
            total_duration += duration
            average_duration = round(total_duration/hooked_count,2)
            if duration < min_duration or min_duration == 0:
                min_duration = round(duration, 2)
            if duration > max_duration:
                max_duration = round(duration, 2)
            while 1:
                valid, location, size = detect_bobber()
                if valid:
                    if location[0] < size * 0.7: #Solving minigame is faster if we stick to the right side
                        pyautogui.mouseDown()
                    else:
                        pyautogui.mouseUp()
                else:
                    if STATE != CASTING:
                        log_info(f"Fish catched! Fishing time: {round(duration, 2)} secs", logger = "Information")
                        catched_count += 1
                        if catched_count >= CATCH_LIMIT:
                            log_info(f"Catch limit reached! Limit: {CATCH_LIMIT}", logger = "Information")
                            log_info(f"Please consider to repair your fishing pole!", logger = "Information")
                            stop(0,0)
                        pyautogui.mouseUp()
                        time.sleep(5) #Waiting for the late notification
                        STATE = CASTING
                        break
        else:
            log_info(f"Bobber not found!", logger = "Information")
            time.sleep(2)
            STATE = CASTING

##########################################################
#
#   These Functions are all Callbacks used by DearPyGui
#
##########################################################

#Sets the spots that will be used for casting
def set_fishing_spots(sender,data):
    global fishing_coordinates,state_left
    stop(0, 0) #stop bot first
    fishing_coordinates = []
    amount_of_choords = get_value("Amount Of Spots")
    for n in range(int(amount_of_choords)):
        n += 1
        temp = []
        log_info(f'[spot:{n}] | Press Spacebar over the spot you want', logger = "Information")
        time.sleep(1)
        while True:
            a = win32api.GetKeyState(0x20)
            if a != state_left:
                state_left = a
                if a < 0:
                    break
            time.sleep(0.001)
        x,y = pyautogui.position()
        temp.append(x)
        temp.append(y)
        fishing_coordinates.append(temp)
        log_info(f'Position: {n} Saved. | {x, y}', logger = "Information")

#Sets tracking zone for image detection
def set_tracking_zone(sender,data):
    global screen_area
    stop(0, 0) #stop bot first
    state_left = win32api.GetKeyState(0x20)
    tracking_zone = []
    log_info(f'Please hold and drag space over tracking zone (top left to bottom right)', logger = "Information")
    while True:
        a = win32api.GetKeyState(0x20)
        if a != state_left:  # Button state changed
            state_left = a
            if a < 0:
                x,y = pyautogui.position()
                tracking_zone.append([x,y])
            else:
                x,y = pyautogui.position()
                tracking_zone.append([x,y])
                break
        time.sleep(0.001)
    start_point = tracking_zone[0]
    end_point = tracking_zone[1]
    screen_area = start_point[0],start_point[1],end_point[0],end_point[1]
    log_info(f'Updated tracking area to {screen_area}', logger = "Information")

#Detects bobber in tracking zone using openCV
def detect_bobber():
    start_time = time.time()
    with mss.mss() as sct:
        base = numpy.array(sct.grab(screen_area))
        base = numpy.flip(base[:, :, :3], 2)  # 1
        base = cv2.cvtColor(base, cv2.COLOR_RGB2BGR)
        bobber = cv2.imread('bobber.png')
        bobber = numpy.array(bobber, dtype=numpy.uint8)
        bobber = numpy.flip(bobber[:, :, :3], 2)  # 1
        bobber = cv2.cvtColor(bobber, cv2.COLOR_RGB2BGR)
        result = cv2.matchTemplate(base,bobber,cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val > detection_threshold:
            if debugmode:
                print(f"Bobber Found!. Match certainty:{max_val}")
                print("%s seconds to calculate" % (time.time() - start_time))
            return [True, max_loc, base.shape[1]]
        else:
            if debugmode:
                print(f"Bobber not found. Match certainty:{max_val}")
                print("%s seconds to calculate" % (time.time() - start_time))
            return [False, max_loc, base.shape[1]]

#Starts the bots threads
def start(data,sender):
    global max_volume,stop_button,STATE
    if stop_button == False:
        log_info(f'Bot started already ah!', logger = "Information")
    else:
        if len(fishing_coordinates) == 0:
            log_info(f'Please set fishing coordinates first!', logger = "Information")
            return
        stop_button = False
        STATE = STARTING
        max_volume = get_value("Set Volume Threshold")
        volume_manager = threading.Thread(name = "VolumeScanner", target = check_volume)
        volume_manager.start()
        log_info(f'Volume Scanner Started', logger = "Information")
        hook_manager = threading.Thread(name = "HookManager", target = cast_hook)
        hook_manager.start()
        log_info(f'Hook Manager Started', logger = "Information")
        log_info(f'Bot Started', logger = "Information")
        STATE = STARTED
    # pyautogui.press("1") #disable auto potion

#Stops the bot and closes active threads
def stop(data,sender):
    global stop_button,STATE
    if stop_button == True:
        log_info(f'Bot stopped already ah!', logger = "Information")
    else:
        STATE = STOPPING
        stop_button = True
        log_info(f'Stopping Hook Manager', logger = "Information")
        log_info(f'Stopping Volume Scanner', logger = "Information")
        pyautogui.mouseUp()
        STATE = STOPPED
        log_info(f'Stopped Bot', logger = "Information")

#Updates Bot Volume
def save_volume(sender, data):
    global max_volume
    max_volume = get_value("Set Volume Threshold")
    log_info(f'Max Volume Updated to: {max_volume}', logger = "Information")

#Set detection threshold
def save_threshold(sender,data):
    global detection_threshold
    detection_threshold = get_value("Set Detection Threshold")
    log_info(f'Detection Threshold Updated to: {detection_threshold}', logger = "Information")

#Set cast timeout
def save_cast_timeout(sender,data):
    global cast_timeout
    cast_timeout = get_value("Set Casting Timeout")
    log_info(f'Casting Timeout Updated to: {cast_timeout}', logger = "Information")

#Set cast power
def save_cast_power(sender,data):
    global cast_power_min, cast_power_max
    cp_min = get_value(sender)[0]
    cp_max = get_value(sender)[1]
    if cp_min > cp_max:
        if cast_power_min != cp_min:
            cp_min = cp_max
        else:
            cp_max = cp_min
        set_value(sender, [cp_min, cp_max])
    cast_power_min = cp_min
    cast_power_max = cp_max
    # log_info(f'Casting Power Updated to: {cast_power_min} - {cast_power_max}', logger = "Information")

#Title rendering
def title_render():
    global bait_counter
    while 1:
        set_main_window_title(f"Fisherman | Status: {STATE} | Fish Hits: {catched_count} / {hooked_count} / {heard_count} / {casted_count} | Duration: {min_duration} - {max_duration} ({average_duration}) | Volume: {total} / {max_volume}")
        time.sleep(0.1)
        if bait_counter == 10:
            bait_counter = 0
            # pyautogui.press("1")

#Saves settings to settings.ini
def save_settings(sender,data):
    fp = open('settings.ini')
    p = configparser.ConfigParser()
    p.read_file(fp)
    p.set('Settings', 'volume_threshold', str(max_volume))
    p.set('Settings', 'tracking_zone', str(screen_area))
    p.set('Settings', 'detection_threshold', str(detection_threshold))
    p.write(open(f'Settings.ini', 'w'))
    log_info(f'Saved New Settings to settings.ini', logger = "Information")

#Settings for DearPyGui window
set_main_window_size(800, 640)
set_style_window_menu_button_position(0)
set_theme("Gold")
set_global_font_scale(1)
set_main_window_resizable(False)

#Creates the DearPyGui Window
with window("Fisherman", width = 784, height = 600):
    set_window_pos("Fisherman", 0, 0)
    add_input_int("Amount Of Spots", max_value = 10, min_value = 0, default_value = 1, tip = "Amount of Fishing Spots")
    add_slider_int2("Set Casting Power", min_value = 20, max_value = 100, default_value = (cast_power_min, cast_power_max), callback = save_cast_power, tip = "Casting power minimum and maximum in percentage")
    add_input_int("Set Casting Timeout", min_value = 20, max_value = 300, default_value = cast_timeout, callback = save_cast_timeout)
    add_input_int("Set Volume Threshold", max_value = 100000, min_value = 0, default_value = int(max_volume), callback = save_volume, tip = "Volume Threshold to trigger catch event")
    add_input_float("Set Detection Threshold", min_value = 0.1, max_value = 1.0, default_value = detection_threshold, callback = save_threshold)
    add_spacing(count = 3)
    add_button("Set Fishing Spots", width = 130, callback = set_fishing_spots, tip = "Starts function that lets you select fishing spots")
    add_same_line()
    add_button("Set Tracking Zone", callback = set_tracking_zone, tip = "Sets zone bot tracks for solving fishing minigame")
    add_same_line()
    add_button("Save Settings", callback = save_settings, tip = "Saves bot settings to settings.ini")
    add_spacing(count = 5)
    add_button("Start Bot", callback = start, tip = "Starts the bot")
    add_same_line()
    add_button("Stop Bot", callback = stop, tip = "Stops the bot")
    add_spacing(count = 5)
    add_logger("Information", log_level = 0)
    log_info(f"Loaded Settings.", logger = "Information")
    log_info(f"Volume Threshold: {max_volume}", logger = "Information")
    log_info(f"Tracking Zone: {screen_area}", logger = "Information")
    log_info(f"Debug Mode: {debugmode}", logger = "Information")
    log_info(f"Detected Input Device: {input_device_name}", logger = "Information")

threading.Thread(name = "TitleRenderer", target = title_render).start()
start_dearpygui()
