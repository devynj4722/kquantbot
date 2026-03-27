import tkinter as tk
import json
import time
import os

class KCIWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KCI Score")
        
        # Make the window frameless and always on top
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry("220x120+100+100")
        
        # Colors
        self.bg_color = "#13151A"  # Dark theme matching DPG
        self.fg_color = "#E2E8F0"
        self.root.configure(bg=self.bg_color)
        
        # Bind mouse events for dragging the borderless window
        self.root.bind("<ButtonPress-1>", self.start_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)
        self.root.bind("<B1-Motion>", self.do_move)
        # Right click to close
        self.root.bind("<Button-3>", lambda e: self.root.destroy())

        # UI Elements
        # Header (Draggable feeling)
        self.header = tk.Label(self.root, text="KCI LIVE [Right-Click to Close]", 
                               bg="#20242D", fg="#808080", font=("Arial", 8))
        self.header.pack(fill=tk.X, pady=(0, 5))
        
        # Main Score
        self.score_label = tk.Label(self.root, text="--.-", 
                                    bg=self.bg_color, fg=self.fg_color, font=("Arial", 36, "bold"))
        self.score_label.pack()
        
        # Tier / Status
        self.tier_label = tk.Label(self.root, text="WAITING FOR DATA", 
                                   bg=self.bg_color, fg="#808080", font=("Arial", 10, "bold"))
        self.tier_label.pack()
        
        # Subtext (Direction & Market)
        self.sub_label = tk.Label(self.root, text="---", 
                                  bg=self.bg_color, fg="#606060", font=("Arial", 8))
        self.sub_label.pack(side=tk.BOTTOM, pady=5)
        
        self.state_file = "kci_state.json"
        
        # Start update loop
        self.update_data()
        self.root.mainloop()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def stop_move(self, event):
        self.x = None
        self.y = None

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def update_data(self):
        try:
            if os.path.exists(self.state_file):
                # Check age
                mtime = os.path.getmtime(self.state_file)
                if time.time() - mtime > 5:
                    self.score_label.config(text="OFF", fg="#808080")
                    self.tier_label.config(text="BOT DISCONNECTED", fg="#808080")
                else:
                    with open(self.state_file, "r") as f:
                        state = json.load(f)
                    
                    kci = state.get("kci", 0.0)
                    tier = state.get("tier", "SKIP")
                    w_sum = state.get("w_sum", 0.0)
                    direction = state.get("direction", "NEUTRAL")
                    countdown = state.get("countdown", "").replace("Time Market closes in ", "")
                    # Using split logic to match the clean DPG formatting
                    
                    self.score_label.config(text=f"{kci:.1f}")
                    self.tier_label.config(text=tier)
                    
                    # Colors
                    if tier == "A-TIER": color = "#00FFAA"
                    elif tier == "B-TIER": color = "#FFAA00"
                    elif "FILTER" in tier: color = "#FF64FF"
                    elif kci > 0: color = "#FF4444"
                    else: color = "#969696"
                    
                    self.score_label.config(fg=color)
                    self.tier_label.config(fg=color)
                    
                    sub = f"Dir: {direction} | Potency: {w_sum:.0f} | Closes: {countdown}"
                    self.sub_label.config(text=sub)
        except Exception as e:
            pass
            
        # Re-run every 500ms
        self.root.after(500, self.update_data)

if __name__ == "__main__":
    KCIWidget()
