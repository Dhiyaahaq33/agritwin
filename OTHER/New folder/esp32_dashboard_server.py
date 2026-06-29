"""
ARUNA Dashboard Bridge Server v3
Baca dari aruna_state.json yang ditulis tumbal.py
Run: python esp32_dashboard_server_v3.py
"""
import asyncio, json, os, threading, time, math, random
import websockets

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aruna_state.json")

state = {
    "zone":"ZONE-A","facility":"GH-INDO-01",
    "temp":22.0,"rh":72.0,"co2":850,"soil":60.0,
    "ec":1.9,"ph":6.4,"ppfd":400,"cold_temp":5.0,
    "flow":1.3,"power_kw":1.85,"energy_kwh":0.0,
    "relay_valve":0,"led_pwm":75,"fan_pwm":50,
    "alarm":0,"alarm_code":0,"uptime_s":0,
    "_source":"waiting"
}

def file_reader_thread():
    """Poll aruna_state.json every second"""
    last_mtime = 0
    while True:
        try:
            if os.path.exists(STATE_FILE):
                mtime = os.path.getmtime(STATE_FILE)
                if mtime != last_mtime:
                    with open(STATE_FILE, 'r') as f:
                        data = json.load(f)
                    state.update(data)
                    last_mtime = mtime
                    print(f"[FILE] T={state.get('temp')} RH={state.get('rh')} CO2={state.get('co2')} src={state.get('_source','?')}")
            else:
                print(f"[FILE] Waiting for {STATE_FILE}... (run tumbal.py dan klik Run Step)")
        except Exception as e:
            print(f"[FILE] Error: {e}")
        time.sleep(1)

async def ws_handler(websocket):
    print(f"[WS] Dashboard connected")
    try:
        while True:
            await websocket.send(json.dumps(state))
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
        print("[WS] Dashboard disconnected")

async def main():
    threading.Thread(target=file_reader_thread, daemon=True).start()
    print(f"[SERVER] Reading from: {STATE_FILE}")
    print(f"[SERVER] WebSocket on ws://localhost:8765")
    print(f"[SERVER] Buka ARUNA_ESP32_Dashboard.html di browser")
    async with websockets.serve(ws_handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())