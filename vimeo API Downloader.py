import sys
import os
import time
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QTextEdit, QFileDialog, QProgressBar, QMessageBox,
                            QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

class VimeoDownloadWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    download_finished = pyqtSignal(bool)

    def __init__(self, access_token, download_path, page_number):
        super().__init__()
        self.access_token = access_token
        self.download_path = download_path
        self.page_number = page_number
        self.download_timeout = 30

    def run(self):
        """
        Execute video download process.
        """
        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}

            # Collect video information
            videos = self._collect_videos(headers, self.page_number)

            total_videos = len(videos)
            self.log_message.emit(f"Starting download of {total_videos} videos...")

            # Download each video
            for index, video in enumerate(videos, 1):
                self._download_video(headers, video, index, total_videos)

            self.download_finished.emit(True)

        except Exception as e:
            self.log_message.emit(f"Download Error: {e}")
            self.download_finished.emit(False)

    def _collect_videos(self, headers, page_number):
        """
        Collect video information from Vimeo API for the specified page.
        """
        videos = []

        try:
            response = requests.get(
                f'https://api.vimeo.com/me/videos?page={page_number}&per_page=50',
                headers=headers,
                timeout=self.download_timeout
            )
            response.raise_for_status()

            page_data = response.json()
            videos = page_data.get('data', [])

        except requests.exceptions.RequestException as api_error:
            self.log_message.emit(f"API Request Error (Page {page_number}): {api_error}")
            raise RuntimeError(f"Failed to fetch videos for page {page_number}")

        self.log_message.emit(f"Found {len(videos)} videos on page {page_number}")
        return videos

    def _download_video(self, headers, video, index, total_videos):
        """
        Download individual video file.
        """
        try:
            video_id = video['uri'].split('/')[-1]
            video_name = video['name']
            download_url = self._get_download_url(headers, video_id)

            if download_url:
                # Sanitize filename to remove invalid characters
                safe_filename = ''.join(c for c in video_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
                file_path = os.path.join(self.download_path, f"{safe_filename}.mp4")

                response = requests.get(download_url, headers=headers, stream=True, timeout=self.download_timeout)
                response.raise_for_status()

                with open(file_path, 'wb') as f:
                    total_length = int(response.headers.get('content-length', 0))
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                            f.flush()

                self.log_message.emit(f"Downloaded video {index}/{total_videos}: {video_name}")
            else:
                self.log_message.emit(f"No download URL found for video {index}/{total_videos}: {video_name}")

        except Exception as download_error:
            self.log_message.emit(f"Download Error for {video_name}: {download_error}")

    def _get_download_url(self, headers, video_id):
        """
        Retrieve video download URL from Vimeo API.
        """
        try:
            response = requests.get(
                f'https://api.vimeo.com/videos/{video_id}',
                headers=headers,
                timeout=self.download_timeout
            )
            response.raise_for_status()

            video_data = response.json()
            for download in video_data['download']:
                if download['quality'] == 'hd':
                    return download['link']

            return None  # No HD download link found

        except requests.exceptions.RequestException as api_error:
            self.log_message.emit(f"API Request Error (Video ID {video_id}): {api_error}")
            return None

class VimeoDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vimeo Downloader")
        self.setGeometry(100, 100, 600, 400)

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Token input section
        token_layout = QHBoxLayout()
        main_layout.addLayout(token_layout)
        token_layout.addWidget(QLabel("Access Token:"))
        self.token_input = QLineEdit()
        token_layout.addWidget(self.token_input)

        # Download path section
        path_layout = QHBoxLayout()
        main_layout.addLayout(path_layout)
        path_layout.addWidget(QLabel("Download Path:"))
        self.path_input = QLineEdit()
        path_layout.addWidget(self.path_input)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_download_path)
        path_layout.addWidget(browse_button)

        # Page Selection Section
        page_layout = QHBoxLayout()
        main_layout.addLayout(page_layout)
        page_layout.addWidget(QLabel("Select Page:"))
        self.page_selector = QComboBox()
        self.page_selector.addItems([str(i) for i in range(1, 199)])
        page_layout.addWidget(self.page_selector)

        # Start download button
        self.start_button = QPushButton("Start Download")
        self.start_button.clicked.connect(self.start_download)
        main_layout.addWidget(self.start_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output)

    def browse_download_path(self):
        """
        Open file dialog to select download directory.
        """
        download_path = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if download_path:
            self.path_input.setText(download_path)

    def start_download(self):
        """
        Initiate video download process with threading.
        """
        access_token = self.token_input.text().strip()
        download_path = self.path_input.text().strip()

        if not access_token:
            QMessageBox.warning(self, "Warning", "Please enter an access token.")
            return

        if not download_path:
            QMessageBox.warning(self, "Warning", "Please select a download path.")
            return

        try:
            # Setup download worker
            self.download_worker = VimeoDownloadWorker(
                access_token, 
                download_path, 
                int(self.page_selector.currentText())
            )

            # Connect signals
            self.download_worker.progress_updated.connect(self.update_progress)
            self.download_worker.log_message.connect(self.log_message)
            self.download_worker.download_finished.connect(self.download_finished)

            # Start download in a separate thread
            self.download_worker.start()

        except Exception as e:
            self.handle_download_error(str(e))

    def update_progress(self, progress):
        """
        Update progress bar with download progress.
        """
        self.progress_bar.setValue(progress)

    def log_message(self, message):
        """
        Append message to log output.
        """
        self.log_output.append(message)

    def download_finished(self, success):
        """
        Handle download completion and display appropriate message.
        """
        if success:
            QMessageBox.information(self, "Information", "Download completed successfully!")
        else:
            QMessageBox.critical(self, "Error", "Download failed. Check the log for details.")

    def handle_download_error(self, error_message):
        """
        Display error message in a critical message box.
        """
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")

def main():
    app = QApplication(sys.argv)
    window = VimeoDownloaderApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()