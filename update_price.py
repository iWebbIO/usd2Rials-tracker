#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime
import re

class USD2RialsUpdater:
    def __init__(self, csv_file_path="USD2Rials.csv"):
        self.csv_file_path = csv_file_path
        self.url = "https://www.tgju.org/profile/price_dollar_rl/history"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def normalize_gregorian_date(self, date_str: str) -> str:

        if not date_str:
            return date_str
        date_str = date_str.strip()
        # حذف زمان در صورت وجود
        date_part = date_str.split()[0]
        # یکنواخت‌سازی جداکننده‌ها
        date_part = date_part.replace('-', '/')
        parsed = None
        for fmt in ('%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                parsed = datetime.strptime(date_part, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parts = re.split(r'[/-]', date_part)
                if len(parts) == 3:
                    if len(parts[0]) == 4 and parts[0].isdigit():
                        # YYYY/M/D
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    elif len(parts[2]) == 4 and parts[2].isdigit():
                        # فرض کاربر: D/M/YYYY
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        raise ValueError
                    parsed = datetime(y, m, d)
            except Exception:
                parsed = None
        if parsed:
            return f"{parsed.month}/{parsed.day}/{parsed.year}"
        return date_str

    def fetch_latest_price(self):
        """از وبسایت tgju آخرین قیمت دلار را دریافت می‌کند"""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # پیدا کردن جدول تاریخچه قیمت
            table = soup.find('table', {'class': 'table widgets-dataTable table-hover text-center history-table'})
            if not table:
                raise ValueError("جدول قیمت در وبسایت پیدا نشد")
            
            # پیدا کردن اولین ردیف داده (بدون هدر)
            first_row = table.find('tbody').find('tr')
            if not first_row:
                raise ValueError("هیچ ردیف داده‌ای در جدول پیدا نشد")
            
            cells = first_row.find_all('td')
            if len(cells) < 8:
                raise ValueError("تعداد ستون‌های مورد انتظار در جدول پیدا نشد")
            
            # استخراج داده‌ها از ردیف اول
            # ترتیب: بیشترین، کمترین، بیشترین، میانگین، تغییر، درصد تغییر، تاریخ میلادی، تاریخ شمسی
            min_price_text = cells[1].get_text(strip=True)  # کمترین قیمت
            max_price_text = cells[2].get_text(strip=True)  # بیشترین قیمت
            raw_gregorian_date = cells[6].get_text(strip=True)  # تاریخ میلادی (خام از سایت)
            gregorian_date = self.normalize_gregorian_date(raw_gregorian_date)  # نرمال‌سازی به Month/Day/Year (M/D/YYYY)
            persian_date = cells[7].get_text(strip=True)    # تاریخ شمسی
            
            # تبدیل قیمت‌ها به عدد
            min_price = int(min_price_text.replace(',', ''))
            max_price = int(max_price_text.replace(',', ''))
            avg_price = (min_price + max_price) // 2
            
            return {
                'date_pr': persian_date,
                'date_gr': gregorian_date,
                'source': 'tgju',
                'price_avg': avg_price
            }
            
        except Exception as e:
            print(f"خطا در دریافت اطلاعات از وبسایت: {str(e)}")
            return None
    
    def get_last_entry(self):
        """آخرین ردیف از فایل CSV را بازمی‌گرداند"""
        try:
            if not os.path.exists(self.csv_file_path):
                return None
                
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                last_row = None
                for row in csv_reader:
                    last_row = row
                return last_row
        except Exception as e:
            print(f"خطا در خواندن آخرین ردیف: {str(e)}")
            return None
    
    def is_new_data(self, new_data, last_entry):
        """بررسی می‌کند که آیا داده جدید است یا نه"""
        if not last_entry:
            return True
        return new_data['date_pr'] != last_entry['date_pr']
    
    def append_to_csv(self, new_data):
        """داده جدید را به فایل CSV اضافه می‌کند"""
        try:
            file_exists = os.path.exists(self.csv_file_path)
            
            with open(self.csv_file_path, 'a', newline='', encoding='utf-8') as file:
                fieldnames = ['date_pr', 'date_gr', 'source', 'price_avg']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                
                # اگر فایل وجود ندارد، هدر را بنویس
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(new_data)
            return True
        except Exception as e:
            print(f"خطا در نوشتن در فایل CSV: {str(e)}")
            return False
    
    def calculate_price_change(self, current_price, previous_price):
        """محاسبه تغییر قیمت و جهت آن"""
        if not previous_price:
            return 0, ""
        
        change = current_price - int(previous_price)
        if change > 0:
            return change, "↗️"
        elif change < 0:
            return change, "↘️"
        else:
            return 0, "➡️"
    
    def update_readme(self, latest_data, last_entry=None):
        """فایل README را با آخرین اطلاعات به‌روزرسانی می‌کند"""
        try:
            # محاسبه تغییر قیمت
            current_price = latest_data['price_avg']
            previous_price = last_entry['price_avg'] if last_entry else None
            price_change, arrow = self.calculate_price_change(current_price, int(previous_price) if previous_price else None)
            
            # ایجاد متن README
            readme_content = f"""# آرشیو قیمت دلار به ریال

## 📊 آخرین اطلاعات

**آخرین به‌روزرسانی:** {latest_data['date_pr']} | **قیمت ثبت شده:** {latest_data['price_avg']:,} ریال {arrow}

"""
            
            if price_change != 0:
                readme_content += f"**تغییر نسبت به روز قبل:** {price_change:+,} ریال\n\n"
            
            readme_content += """---

## 🔍 درباره مخزن

این مخزن حاوی اطلاعات تاریخچه قیمت دلار آمریکا به ریال ایران است که به صورت خودکار و روزانه از سایت معتبر **tgju.org** جمع‌آوری می‌شود.
داده‌ها از تاریخ ۷ مهرماه ۱۳۶۰ تا به امروز هستند.

داده‌های اولیه این مخزن از سایت [مدرسه دقیقه](https://d-learn.ir/usd-price/) برداشته شده‌است و به صورت دوره‌ای این داده‌ در همین لینک بارگذاری می‌شود.

### 📋 توضیحات و فرایند:
- **به‌روزرسانی خودکار**: هر روز ساعت ۱۱:۰۰ صبح به وقت تهران
- **تاریخ دوگانه**: شامل تاریخ شمسی و میلادی
- **قیمت میانگین**: محاسبه شده از کمترین و بیشترین قیمت روز
- **نمایش تغییرات**: مقایسه با روز قبل همراه با نشانگر در مخزن

### 📊 ساختار داده‌ها:
| ستون | توضیح |
|------|-------|
| `date_pr` | تاریخ شمسی (فارسی) |
| `date_gr` | تاریخ میلادی (گریگورین) |
| `source` | منبع اطلاعات (tgju) |
| `price_avg` | میانگین قیمت روز (ریال) |

---
"""
            
            with open('README.md', 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            return True
        except Exception as e:
            print(f"خطا در به‌روزرسانی README: {str(e)}")
            return False
    
    def run(self):
        """اجرای فرآیند اصلی به‌روزرسانی"""
        print("🔄 شروع فرآیند به‌روزرسانی قیمت دلار...")
        
        # دریافت آخرین قیمت از وبسایت
        latest_data = self.fetch_latest_price()
        if not latest_data:
            print("❌ خطا در دریافت اطلاعات از وبسایت")
            return False
        
        print(f"📊 قیمت جدید دریافت شد: {latest_data['date_pr']} - {latest_data['price_avg']:,} ریال")
        
        # دریافت آخرین ردیف از فایل
        last_entry = self.get_last_entry()
        
        # بررسی جدید بودن داده
        if self.is_new_data(latest_data, last_entry):
            # اضافه کردن به CSV
            if self.append_to_csv(latest_data):
                print("✅ داده جدید با موفقیت به فایل CSV اضافه شد")
                
                # به‌روزرسانی README
                if self.update_readme(latest_data, last_entry):
                    print("✅ فایل README با موفقیت به‌روزرسانی شد")
                else:
                    print("⚠️ خطا در به‌روزرسانی README")
                
                return True
            else:
                print("❌ خطا در اضافه کردن داده به فایل")
                return False
        else:
            print("ℹ️ داده جدیدی برای اضافه کردن وجود ندارد")
            # حتی اگر داده جدید نباشد، README را به‌روزرسانی کن
            self.update_readme(latest_data, last_entry)
            return True

if __name__ == "__main__":
    updater = USD2RialsUpdater()
    success = updater.run()
    exit(0 if success else 1)
