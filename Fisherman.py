import pyautogui,pyaudio,audioop,threading,time,win32api,configparser,mss,mss.tools,cv2,numpy,win32gui,win32con,win32ui
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
coords = []

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

#Sound Volume
total = 0

#Current Bot State
STATE = IDLE

#Thread Stopper
stop_button = False

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

def _get_windows_bytitle(title_text, exact = False):
    def _window_callback(hwnd, all_windows):
        all_windows.append((hwnd, win32gui.GetWindowText(hwnd)))
    windows = []
    win32gui.EnumWindows(_window_callback, windows)
    # for w in windows:
    #     print(w)
    if exact:
        return [hwnd for hwnd, title in windows if title_text == title]
    else:
        return [hwnd for hwnd, title in windows if title_text in title]

#refactor mouse click to use win32gui for background clicking
test = _get_windows_bytitle("Albion Online Client")
print(f"get window test: {test}")
hWnd = win32gui.FindWindow(None, "Albion Online Client")
print(f"get window handler: {hWnd}")
lParam = 0

child_handles = []
def getchildren(hwnd, param):
    child_handles.append(hwnd)

win32gui.EnumChildWindows(hWnd, getchildren, None)
print(f"children: {child_handles}")

rect = win32gui.GetWindowRect(hWnd)
print(f"get window rect: {rect}")
window_pos_x = rect[0]
window_pos_y = rect[1]
window_width = rect[2] - window_pos_x
window_height = rect[3] - window_pos_y
print("Window %s:" % win32gui.GetWindowText(hWnd))
print("\tLocation: (%d, %d)" % (window_pos_x, window_pos_y))
print("\tSize: (%d, %d)" % (window_width, window_height))

def test_click(x, y):
    print(f"window handler: {hWnd}")
    print(f"moving mouse and click to {x, y} inside the window")
    lParam = win32api.MAKELONG(x, y)
    print(f"long param: {lParam}")
    win32api.SetCursorPos((x,y))
    # win32api.PostMessage(hWnd, win32con.WM_MOUSEMOVE, 0, lParam);
    # time.sleep(.05)
    win32api.PostMessage(hWnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam);
    time.sleep(.05)
    win32api.PostMessage(hWnd, win32con.WM_LBUTTONUP, 0, lParam);
    # time.sleep(5)

# test_click(100, 100)
# test_click(200, 100)
# test_click(200, 200)
# test_click(100, 200)

# 1024x768: 426,381 - 599,420

def screenshot(x, y):
    try:
        hDC = win32gui.GetWindowDC(hWnd)
        myDC = win32ui.CreateDCFromHandle(hDC)
        newDC = myDC.CreateCompatibleDC()

        myBitMap = win32ui.CreateBitmap()
        myBitMap.CreateCompatibleBitmap(myDC, window_width, window_height)

        newDC.SelectObject(myBitMap)

        win32gui.SetForegroundWindow(hWnd)
        time.sleep(1.2) #lame way to allow screen to draw before taking shot
        newDC.BitBlt((0,0), (window_width, window_height), myDC, (0,0), win32con.SRCCOPY)
        # newDC.BitBlt((0,0), (599-426, 420-381), myDC, (426, 381), win32con.SRCCOPY)
        myBitMap.Paint(newDC)
        myBitMap.SaveBitmapFile(newDC, f"{round(time.time(), 0)}_test.jpg")
    except Exception as e:
        print(f"Error: {e}")

# screenshot(0, 0)

##########################################################
#
#   These Functions handle bot state / minigame handling
#
##########################################################

#Scans the current input volume
def check_volume():
    global total,max_volume,stop_button
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,channels=2,rate=44100,input=True,frames_per_buffer=1024)
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
    return random.choice(coords)

#Runs the casting function
def cast_hook():
    global STATE,cast_time,casted_count,lParam
    last_state = ""
    while 1:
        time.sleep(0.5)
        if STATE != last_state:
            print(f"Cast Hook Check! Stop: {stop_button}, State: {STATE}")
            last_state = STATE
        if stop_button == False:
            if STATE == CASTING or STATE == STARTED:
                x, y = get_new_spot()
                # lParam = win32api.MAKELONG(x, y)
                log_info(f"Get new coordinate: {x,y}", logger = "Information")
                time.sleep(1.5)
                test_click(x, y)
                # win32gui.PostMessage(hWnd, win32con.WM_MOUSEMOVE, 0, lParam);
                # pyautogui.mouseUp()
                # win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
                # pyautogui.moveTo(x,y,tween=pyautogui.linear,duration=0.2)
                # time.sleep(0.2)
                # pyautogui.mouseDown()
                # win32gui.PostMessage(hWnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                time.sleep(random.uniform(cast_power_min*9/1000, cast_power_max*9/1000))
                # pyautogui.mouseUp()
                # win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
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
                    # pyautogui.mouseDown()
                    win32gui.PostMessage(hWnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                    time.sleep(0.1)
                    # pyautogui.mouseUp()
                    win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
                    time.sleep(2)
        else:
            break

#Uses obj detection with OpenCV to find and track bobbers left / right coords
def do_catch():
    global STATE,heard_count,hooked_count,catched_count,bait_counter,cast_time,total_duration,average_duration,min_duration,max_duration
    if STATE != CASTING and STATE != STARTED:
        log_info(f"Hooked sound detected!", logger = "Information")
        heard_count += 1
        STATE = CATCHING
        # pyautogui.mouseDown()
        win32gui.PostMessage(hWnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        # pyautogui.mouseUp()
        win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
        duration = time.time() - cast_time
        #Initial scan. Waits for bobber to appear
        time.sleep(0.5)
        valid,location,size = Detect_Bobber()
        if valid == "TRUE":
            log_info(f"Bobber detected! Starting to catch fish", logger = "Information")
            hooked_count += 1
            bait_counter += 1
            total_duration += duration
            average_duration = round(total_duration/hooked_count,2)
            if duration < min_duration or min_duration == 0:
                min_duration = round(duration, 2)
            if duration > max_duration:
                max_duration = round(duration, 2)
            while 1:
                valid,location,size = Detect_Bobber()
                if valid == "TRUE":
                    if location[0] < size * 0.7: #Solving minigame is faster if we stick to the right side
                        # pyautogui.mouseDown()
                        win32gui.PostMessage(hWnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                    else:
                        # pyautogui.mouseUp()
                        win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
                else:
                    if STATE != CASTING:
                        log_info(f"Fish catched! Fishing time: {round(duration, 2)} secs", logger = "Information")
                        catched_count += 1
                        if catched_count >= CATCH_LIMIT:
                            log_info(f"Catch limit reached! Limit: {CATCH_LIMIT}", logger = "Information")
                            log_info(f"Please consider to repair your fishing pole!", logger = "Information")
                            stop(0,0)
                        # pyautogui.mouseUp()
                        win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
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

#Generates the areas used for casting
def generate_coords(sender,data):
    global coords,STATE,state_left
    amount_of_choords = get_value("Amount Of Spots")
    for n in range(int(amount_of_choords)):
        n = n+1
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
        x, y = win32gui.GetCursorPos()
        log_info(f'Original Position: {x, y}', logger = "Information")
        time.sleep(5)
        test_click(x, y)
        time.sleep(5)
        x = x - window_pos_x
        y = y - window_pos_y
        temp.append(x)
        temp.append(y)
        coords.append(temp)
        log_info(f'Position: {n} Saved. | {x, y}', logger = "Information")
        test_click(x, y)

#Sets tracking zone for image detection
def Grab_Screen(sender,data):
    global screen_area
    state_left = win32api.GetKeyState(0x20)
    image_coords = []
    log_info(f'Please hold and drag space over tracking zone (top left to bottom right)', logger = "Information")
    while True:
        a = win32api.GetKeyState(0x20)
        if a != state_left:  # Button state changed
            state_left = a
            if a < 0:
                x,y = pyautogui.position()
                image_coords.append([x,y])
            else:
                x,y = pyautogui.position()
                image_coords.append([x,y])
                break
        time.sleep(0.001)
    start_point = image_coords[0]
    end_point = image_coords[1]
    screen_area = start_point[0],start_point[1],end_point[0],end_point[1]
    log_info(f'Updated tracking area to {screen_area}', logger = "Information")

#Detects bobber in tracking zone using openCV
def Detect_Bobber():
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
        if max_val > 0.5:
            print(f"Bobber Found!. Match certainty:{max_val}")
            print("%s seconds to calculate" % (time.time() - start_time))
            return ["TRUE",max_loc,base.shape[1]]
        else:
            print(f"Bobber not found. Match certainty:{max_val}")
            print("%s seconds to calculate" % (time.time() - start_time))
            return ["FALSE",max_loc,base.shape[1]]

#Starts the bots threads
def start(data,sender):
    global max_volume,stop_button,STATE
    STATE = STARTING
    stop_button = False
    # volume_manager = threading.Thread(target = check_volume)
    hook_manager = threading.Thread(target = cast_hook)
    if stop_button == False:
        max_volume = get_value("Set Volume Threshold")
        if len(coords) == 0:
            log_info(f'Please Select Fishing Coords first', logger = "Information")
            return
        else:
            # volume_manager.start()
            log_info(f'Volume Scanner Started', logger = "Information")
            hook_manager.start()
            log_info(f'Hook Manager Started', logger = "Information")
            log_info(f'Bot Started', logger = "Information")
    STATE = STARTED
    # pyautogui.press("1")

#Stops the bot and closes active threads
def stop(data,sender):
    global stop_button,STATE
    STATE = STOPPING
    stop_button = True
    log_info(f'Stopping Hook Manager', logger = "Information")
    log_info(f'Stopping Volume Scanner', logger = "Information")
    # pyautogui.mouseUp()
    win32gui.PostMessage(hWnd, win32con.WM_LBUTTONUP, None, lParam)
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

#Title Tracking
def Setup_title():
    global bait_counter
    while 1:
        set_main_window_title(f"Fisherman | Status: {STATE} | Fish Hits: {catched_count} / {hooked_count} / {heard_count} / {casted_count} | Duration: {min_duration} - {max_duration} ({average_duration}) | Volume:{total} / {max_volume}")
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
    add_button("Set Fishing Spots", width = 130, callback = generate_coords, tip = "Starts function that lets you select fishing spots")
    add_same_line()
    add_button("Set Tracking Zone", callback = Grab_Screen, tip = "Sets zone bot tracks for solving fishing minigame")
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

threading.Thread(target = Setup_title).start()
start_dearpygui()
