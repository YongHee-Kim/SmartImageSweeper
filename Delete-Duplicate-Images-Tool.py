###Developed by Abhishek Satpathy (www.abhisat.com)
import os
import hashlib
from PIL import Image
import threading
import queue
from tkinter import Tk, filedialog, messagebox, Toplevel, Label
from tkinter.ttk import Progressbar
from datetime import datetime

def get_image_hash(image_path):
    try:
        with Image.open(image_path) as img:
            img = img.resize((256, 256)).convert('RGB')
            img_bytes = img.tobytes()
            return hashlib.md5(img_bytes).hexdigest()
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return None

def delete_duplicate_images(folder_path, progress_queue):
    hashes = {}
    deleted = []

    all_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                all_files.append(os.path.join(root, file))

    total = len(all_files)
    for idx, file_path in enumerate(all_files, 1):
        img_hash = get_image_hash(file_path)

        if img_hash:
            if img_hash in hashes:
                try:
                    os.remove(file_path)
                    deleted.append(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")
            else:
                hashes[img_hash] = file_path

        progress_queue.put((idx, total))

    progress_queue.put(("done", deleted))

def write_log(deleted_files, log_folder):
    if not deleted_files:
        return
    log_path = os.path.join(log_folder, "deleted_images_log.txt")
    with open(log_path, "a") as f:
        f.write(f"\n--- Log generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        for file in deleted_files:
            f.write(file + "\n")
        f.write("--- End of log ---\n\n")

def show_progress_window(folder_path):
    progress_window = Toplevel()
    progress_window.title("Processing Images")
    progress_window.geometry("400x100")
    progress_window.resizable(False, False)

    label = Label(progress_window, text="Starting...", font=("Arial", 12))
    label.pack(pady=10)

    progress = Progressbar(progress_window, orient="horizontal", length=300, mode="determinate")
    progress.pack(pady=5)

    progress_queue = queue.Queue()

    def update_progress():
        try:
            while not progress_queue.empty():
                data = progress_queue.get_nowait()
                if isinstance(data, tuple):
                    if data[0] == "done":
                        deleted_files = data[1]
                        progress_window.destroy()
                        write_log(deleted_files, folder_path)
                        if deleted_files:
                            messagebox.showinfo("Done", f"Deleted {len(deleted_files)} duplicate images.\nLog saved in folder.")
                        else:
                            messagebox.showinfo("Done", "No duplicate images found.")
                        return
                    else:
                        current, total = data
                        percent = int((current / total) * 100)
                        progress["value"] = percent
                        label.config(text=f"Processing {current}/{total} images...")
        except queue.Empty:
            pass
        progress_window.after(100, update_progress)

    threading.Thread(target=delete_duplicate_images, args=(folder_path, progress_queue), daemon=True).start()
    update_progress()

def select_folder_and_process():
    folder_path = filedialog.askdirectory(title="Select Folder with Images")
    if not folder_path:
        return
    show_progress_window(folder_path)

if __name__ == "__main__":
    root = Tk()
    root.withdraw()
    select_folder_and_process()
    root.mainloop()
###Developed by Abhishek Satpathy (www.abhisat.com)