from tkinter import filedialog
import subprocess
import os
import shutil
from player import play_video

# Select video file
def select_video_file():
    """Use Windows file picker to select video file"""
    try:
        import tkinter as tk
    except ImportError:
        return None
        
    root = tk.Tk()
    root.withdraw()
    
    title = "Select Video File"
    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("All Files", "*.*")]
    )
    root.destroy()
    return file_path

# Audio playback inquiry
def ask_audio_play():
    while True:
        choice = input("Play audio? (Press Enter to play, type 'n' to skip): ").strip().lower()
        if choice == "" or choice == "y":
            return True
        elif choice == "n":
            return False
        else:
            print("Invalid input, please enter 'y' or 'n'")

# Display mode inquiry
def ask_color_mode():
    while True:
        choice = input("Use color mode? (Press Enter for grayscale, type 'y' for color): ").strip()
        if choice == "" or choice == "n":
            return False
        elif choice == "y":
            return True
        else:
            print("Invalid input, please enter 'y' or 'n'")

# Audio playback
def play_audio(video_path):
    try:
        ffplay_path = shutil.which("ffplay")
        if ffplay_path is None:
            ffplay_path = os.path.join(os.path.dirname(__file__), "ffmpeg", "bin", "ffplay.exe")
        
        if not os.path.exists(ffplay_path) and shutil.which("ffplay") is None:
            print("Warning: ffplay.exe not found, playing without audio")
            return None
            
        process = subprocess.Popen([
            ffplay_path, 
            "-nodisp",
            "-autoexit",
            "-vn",
            video_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return process
    except Exception as e:
        print(f"Warning: Cannot start audio playback: {str(e)}")
        return None

# Main program logic
def main():
    # Language selection removed
    
    video_path = select_video_file()
    if not video_path:
        print("No video file selected, program exiting")
        return
    
    play_audio_flag = ask_audio_play()
    use_color = ask_color_mode()
    
    title_msg = "=== PyAsciiFilm Video Player ==="
    selected_msg = f"Selected video: {video_path}"
    
    print(title_msg)
    print(selected_msg)
    
    audio_process = None
    try:
        if play_audio_flag:
            audio_process = play_audio(video_path)
        
        play_video(video_path, use_color)
        
    except Exception as e:
        print(f"\n[Error] Exception during playback: {str(e)}")
    finally:
        if audio_process and audio_process.poll() is None:
            audio_process.terminate()
            try:
                audio_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                audio_process.kill()
        print("\nProgram exited")

if __name__ == "__main__":
    main()