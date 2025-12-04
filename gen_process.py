from utils.file_process import read_json

def which_device() -> str:
    return "xinertel"


def load_process_example(device_name: str):
    if device_name == "xinertel":
        test_process = read_json("examples/xinertel_test_process.json")
    
    