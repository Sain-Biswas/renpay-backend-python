import uuid
from app.models.transaction import TransactionCreate, TransactionType, TransactionUpdate, Transaction
from app.models.account import AccountUpdate, Account
from app.models.preferences import UserPreferencesUpdate
from app.models.inventory import InventoryItemUpdate
from app.models.sales_report import SalesReportBase, ReportType
from datetime import date, datetime, timezone

def test_transaction_models():
    print("\nTesting Transaction models...")
    
    # Test TransactionCreate
    t = TransactionCreate(
        amount=100.00, 
        description='Test transaction', 
        transaction_type=TransactionType.EXPENSE, 
        from_account_id=uuid.uuid4()
    )
    print(f"TransactionCreate: {t.model_dump_json(indent=2)}")
    
    # Test TransactionUpdate
    t_update = TransactionUpdate(description="Updated description")
    print(f"TransactionUpdate: {t_update.model_dump_json(indent=2)}")

def test_account_models():
    print("\nTesting Account models...")
    
    # Test AccountUpdate
    a_update = AccountUpdate(name="Updated account name")
    print(f"AccountUpdate: {a_update.model_dump_json(indent=2)}")

def test_preferences_models():
    print("\nTesting Preferences models...")
    
    # Test UserPreferencesUpdate
    p_update = UserPreferencesUpdate(theme="dark")
    print(f"UserPreferencesUpdate: {p_update.model_dump_json(indent=2)}")

def test_inventory_models():
    print("\nTesting Inventory models...")
    
    # Test InventoryItemUpdate
    i_update = InventoryItemUpdate(name="Updated item name")
    print(f"InventoryItemUpdate: {i_update.model_dump_json(indent=2)}")

def test_sales_report_models():
    print("\nTesting SalesReport models...")
    
    # Test SalesReportBase
    today = date.today()
    tomorrow = date(today.year, today.month, today.day + 1)
    s_report = SalesReportBase(
        report_type=ReportType.DAILY,
        start_date=today,
        end_date=today
    )
    print(f"SalesReportBase: {s_report.model_dump_json(indent=2)}")

if __name__ == "__main__":
    print("Testing Pydantic models with model_validator...")
    
    try:
        test_transaction_models()
        test_account_models()
        test_preferences_models()
        test_inventory_models()
        test_sales_report_models()
        
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"\nError testing models: {e}") 