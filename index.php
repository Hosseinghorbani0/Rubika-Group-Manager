<?php
/**
 * webhook.php - Rubika Bot Webhook Receiver
 * Based on official rubka documentation: https://github.com/Mahdy-Ahmadi/rubka/blob/main/webhook.md
 *
 * آپدیت‌ها را از سرور روبیکا دریافت کرده و در فایل message.json ذخیره می‌کند.
 * سپس اسکریپت Python آن فایل را می‌خواند و پردازش می‌کند.
 */

$count = 50;   // حداکثر تعداد پیام ذخیره‌شده در فایل (FIFO)
header("Content-Type: application/json");

// مسیر فایل JSON که آپدیت‌ها در آن ذخیره می‌شوند
$file_name = "message.json";
$file_path = __DIR__ . "/" . $file_name;

// ساخت URL کامل فایل برای نمایش در تست GET
$protocol = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? "https" : "http";
$host     = $_SERVER['HTTP_HOST'];
$script_dir = rtrim(dirname($_SERVER['SCRIPT_NAME']), '/');
$file_url = $protocol . "://" . $host . $script_dir . "/" . $file_name;

// ========================= درخواست GET (تست سلامت) =========================
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode([
        "status"  => "active",
        "message" => "Rubika Webhook is running. POST requests are accepted.",
        "url"     => $file_url
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
    exit;
}

// ========================= دریافت و اعتبارسنجی JSON =========================
$input = file_get_contents("php://input");
if (empty($input)) {
    http_response_code(400);
    echo json_encode(["status" => "error", "message" => "No data received"], JSON_PRETTY_PRINT);
    exit;
}

$data = json_decode($input, true);
if ($data === null) {
    http_response_code(400);
    echo json_encode(["status" => "error", "message" => "Invalid JSON: " . json_last_error_msg()], JSON_PRETTY_PRINT);
    exit;
}

// اضافه کردن timestamp برای inline_message
if (isset($data['inline_message'])) {
    $data['inline_message']['time'] = time();
}

// ساخت آبجکت ورودی جدید
$new_entry = [
    "received_at" => date("Y-m-d H:i:s"),
    "data"        => $data
];

// ========================= نوشتن در فایل با قفل (thread-safe) =========================
$success    = false;
$max_retries = 5;
$retry_delay = 500; // microseconds

for ($attempt = 1; $attempt <= $max_retries; $attempt++) {
    $fp = fopen($file_path, 'c+');
    if (!$fp) {
        usleep($retry_delay * $attempt);
        continue;
    }

    if (flock($fp, LOCK_EX)) {
        $current_content = '';
        $file_size = filesize($file_path);
        if ($file_size > 0) {
            $current_content = fread($fp, $file_size);
        }

        $messages = [];
        if (!empty($current_content)) {
            $decoded = json_decode($current_content, true);
            if (is_array($decoded)) {
                $messages = $decoded;
            }
        }

        // اضافه کردن ورودی جدید
        $messages[] = $new_entry;

        // نگه داشتن فقط آخرین $count پیام (FIFO)
        if (count($messages) > $count) {
            $messages = array_slice($messages, -$count);
        }

        ftruncate($fp, 0);
        rewind($fp);
        $json_output = json_encode($messages, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
        $write_result = fwrite($fp, $json_output);

        if ($write_result !== false) {
            $success = true;
        }

        flock($fp, LOCK_UN);
        fclose($fp);

        if ($success) break;
    } else {
        fclose($fp);
    }

    usleep($retry_delay * $attempt);
}

// ========================= پاسخ به Rubika =========================
if (!$success) {
    http_response_code(503);
    echo json_encode([
        "status"  => "error",
        "message" => "Failed to write data after {$max_retries} attempts"
    ], JSON_PRETTY_PRINT);
    exit;
}

echo json_encode([
    "status"  => "ok",
    "message" => "Update received and stored",
    "url"     => $file_url
], JSON_PRETTY_PRINT);
