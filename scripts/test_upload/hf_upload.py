import argparse
import time

from huggingface_hub import HfApi, create_repo

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new dataset repo on Hugging Face Hub")
    parser.add_argument("repo_id", help="Name of the dataset repo")
    parser.add_argument("--local-dir", help="Path to the local directory containing the dataset")
    parser.add_argument("--token", help="Hugging Face Hub token")
    args = parser.parse_args()

    st = time.time()

    api = HfApi(token=args.token)
    try:
        create_repo(
            repo_id=args.repo_id,
            repo_type="dataset",
            token=args.token,
            exist_ok=True,
        )
        print(f"Repository {args.repo_id} is ready.")
    except Exception as e:
        print(f"Warning: Could not create repo (may already exist): {e}")

    # Step 4: 推送数据集到 Hub
    print("Uploading dataset to Hugging Face Hub...")
    api.upload_folder(
        repo_id=args.repo_id,
        token=args.token,
        folder_path=args.local_dir,
        repo_type="dataset",
    )

    print(f"Dataset uploaded in {time.time() - st:.2f}s.")

"""
python scripts/test_upload/hf_upload.py RoboCOIN/test_upload_0 --local-dir /mnt/nas/synnas/docker2/test_upload/tar_test.zip --token 

python scripts/test_upload/hf_upload.py RoboCOIN/test_upload_1 --local-dir /mnt/nas/synnas/docker2/test_upload/tar1.zip --token 
python scripts/test_upload/hf_upload.py RoboCOIN/test_upload_2 --local-dir /mnt/nas/synnas/docker2/test_upload/tar2.zip --token 
python scripts/test_upload/hf_upload.py RoboCOIN/test_upload_3 --local-dir /mnt/nas/synnas/docker2/test_upload/tar3.zip --token 
"""
