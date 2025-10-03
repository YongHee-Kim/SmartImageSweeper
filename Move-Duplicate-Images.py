###Developed by Abhishek Satpathy (www.abhisat.com)
import os
import queue
import threading
from datetime import datetime
from tkinter import Tk, filedialog, messagebox, Toplevel, Label
from tkinter.ttk import Progressbar

import cv2
import imagehash
from PIL import Image
import shutil
import pillow_heif  # Add this import to enable HEIC support in Pillow
from concurrent.futures import ThreadPoolExecutor


# This function will calculate the blur score according to the Laplacian Rule
def calculate_blur(image_path):
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0
        return cv2.Laplacian(img, cv2.CV_64F).var()
    except Exception as e:
        print(f"Error calculating blur for {image_path}: {e}")
        return 0

# This function will cache the score of images
def get_best_image(images):
    blur_scores = {img: calculate_blur(img) for img in images}
    return max(blur_scores, key=blur_scores.get)


from imagehash import phash

# Ensure HEIC support is registered with Pillow
pillow_heif.register_heif_opener()

def collect_all_images(folder_path):
    """Collect all image file paths from the given folder."""
    all_files = []
    for path, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.heic')):  # Added .heic
                all_files.append(os.path.join(path, file))
    return all_files

def flag_duplicate_images(all_files, progress_queue, hash_threshold=5):
    """Identify and group duplicate images based on perceptual hash similarity."""
    duplicate_groups = []
    total = len(all_files)

    for idx, file_path in enumerate(all_files, 1):
        try:
            with Image.open(file_path) as img:
                current_hash = phash(img)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        found_similar = False
        for existing_hash, file_list in duplicate_groups:
            if current_hash - existing_hash <= hash_threshold:
                file_list.append(file_path)
                found_similar = True
                break

        if not found_similar:
            duplicate_groups.append((current_hash, [file_path]))

        progress_queue.put((idx, total))

    return duplicate_groups

def flag_duplicate_images_threaded(all_files, progress_queue, hash_threshold=5):
    """Identify and group duplicate images based on perceptual hash similarity using threading."""
    duplicate_groups = []
    total = len(all_files)
    lock = threading.Lock()

    def process_file(idx, file_path):
        try:
            with Image.open(file_path) as img:
                current_hash = phash(img)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        found_similar = False
        with lock:  # Ensure thread-safe access to shared data
            for existing_hash, file_list in duplicate_groups:
                if current_hash - existing_hash <= hash_threshold:
                    file_list.append(file_path)
                    found_similar = True
                    break

            if not found_similar:
                duplicate_groups.append((current_hash, [file_path]))

        progress_queue.put((idx, total))

    with ThreadPoolExecutor() as executor:
        for idx, file_path in enumerate(all_files, 1):
            executor.submit(process_file, idx, file_path)

    return duplicate_groups

def get_file_creation_date(file_path):
    """Get the creation date of a file."""
    try:
        creation_time = os.path.getctime(file_path)
        return datetime.fromtimestamp(creation_time)
    except Exception as e:
        print(f"Error getting creation date for {file_path}: {e}")
        return None

def move_duplicates(duplicate_groups, folder_path, dup_bin_path):
    """Move duplicate images to the dup_bin folder while preserving folder structure and checking creation dates."""
    moved = []

    for _, duplicates in duplicate_groups:
        if len(duplicates) > 1:
            best_image = get_best_image(duplicates)
            best_image_date = get_file_creation_date(best_image)

            if not best_image_date or best_image_date.year < 2010:
                print(f"Skipping group with files created before 2010 or invalid date: {duplicates}")
                continue

            for img in duplicates:
                if img != best_image:
                    try:
                        img_date = get_file_creation_date(img)

                        # Ensure the photo was taken on the same date
                        if img_date and img_date.date() == best_image_date.date():
                            relative_path = os.path.relpath(os.path.dirname(img), start=folder_path)
                            destination_dir = os.path.join(dup_bin_path, relative_path)
                            os.makedirs(destination_dir, exist_ok=True)

                            destination = os.path.join(destination_dir, os.path.basename(img))
                            shutil.move(img, destination)
                            moved.append(img)
                            print(f"Moved: {img} to {destination}")
                        else:
                            print(f"Skipped {img} due to mismatched creation date.")
                    except Exception as e:
                        print(f"Failed to move {img}: {e}")
            print(f"Kept: {best_image}\n")

    return moved

def move_duplicate_images(folder_path, progress_queue):
    """Main function to move duplicate images."""
    # Ask the user to select the directory for storing duplicates
    # root = Tk()
    # root.withdraw()  # Hide the root window
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dup_bin_path = filedialog.askdirectory(title="Select Folder to Store Duplicates", initialdir=script_dir)
    if not dup_bin_path:
        print("No folder selected for storing duplicates. Operation cancelled.")
        return

    os.makedirs(dup_bin_path, exist_ok=True)

    all_files = collect_all_images(folder_path)
    duplicate_groups = flag_duplicate_images_threaded(all_files, progress_queue)
    moved = move_duplicates(duplicate_groups, folder_path, dup_bin_path)

    print(f"\nTotal duplicates moved: {len(moved)}")
    progress_queue.put(("done", moved))



def write_log(moved_files, log_folder):
    if not moved_files:
        return
    log_path = os.path.join(log_folder, "deleted_images_log.txt")
    with open(log_path, "a") as f:
        f.write(f"\n--- Log generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        for file in moved_files:
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

    # Updated this function because it was getting stuck after processing as it was not stopping after detecting completion
    def update_progress():
        while not progress_queue.empty():
            data = progress_queue.get_nowait()
            if isinstance(data, tuple):
                if data[0] == "done":
                    moved_files = data[1]
                    write_log(moved_files, folder_path)
                    if moved_files:
                        messagebox.showinfo("Done",
                                            f"Moved {len(moved_files)} duplicate images to 'dup_bin' folder.\nLog saved in folder.")
                    else:
                        messagebox.showinfo("Done", "No duplicate images found.")
                    progress_window.destroy()
                    root.quit()
                    return  # Exit the loop and stop calling after()
                else:
                    current, total = data
                    percent = int((current / total) * 100)
                    progress["value"] = percent
                    label.config(text=f"Processing {current}/{total} images...")

        # Only continue the loop if "done" wasn't found yet
        progress_window.after(100, update_progress)

    threading.Thread(target=move_duplicate_images, args=(folder_path, progress_queue), daemon=True).start()
    update_progress()

def select_folder_and_process():
    # hardcoded initial directory 
    init_folder = os.environ.get("OneDrive")
    folder_path = filedialog.askdirectory(title="Select Folder with Images", initialdir=init_folder)
    if not folder_path:
        return
    show_progress_window(folder_path)

if __name__ == "__main__":
    root = Tk()
    root.withdraw()
    select_folder_and_process()
    root.mainloop()
