import sys
import os
import paramiko

def download_from_sftp(hostname, port, username, password, remote_path, local_path):
    # Connect to the SFTP server
    transport = paramiko.Transport((hostname, port))
    transport.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    
    # Create local directory if it doesn't exist
    local_dir = os.path.dirname(local_path)
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    try:
        # Download the file
        sftp.get(remote_path, local_path)
        print(f"File downloaded successfully from {remote_path} to {local_path}")
    except Exception as e:
        print(f"Error downloading file: {e}")
    finally:
        # Close the connection
        sftp.close()
        transport.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sen2cor3_download.py local_path")
        sys.exit(1)
        
    local_path = sys.argv[1]
    local_path = os.path.join(local_path, 'sen2cor_3.1.0_python_3.10_20240313.zip')
    
    hostname = "sftp.telespazio.fr"
    port = 22  # default SFTP port is 22
    username = 'sen2cor3'
    password = '4sen2like'
    remote_path = '/upload/Sen2Cor-3.01.00/Software/sen2cor_3.1.0_python_3.10_20240313.zip'
    
    download_from_sftp(hostname, port, username, password, remote_path, local_path)