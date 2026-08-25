from core.runner import run_dataset


if __name__ == "__main__":

    result = run_dataset(
        "daily_upi_transactions"
    )

    print(result)