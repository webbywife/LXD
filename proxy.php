<?php
/**
 * PHP Reverse Proxy for Gunicorn
 * Cloudways Varnish strips cookies from non-.php request URLs.
 * Starting a PHP session creates a PHPSESSID cookie that signals
 * Varnish to bypass caching and pass all cookies through.
 */

// PHP session ensures PHPSESSID cookie exists → Varnish passes cookies through
session_start();
session_write_close();

$backend = 'http://127.0.0.1:9090';
$path = $_SERVER['REQUEST_URI'] ?? '/';
$method = $_SERVER['REQUEST_METHOD'];
$url = $backend . $path;

// Debug logging (temporary)
$raw_cookie_for_log = $_SERVER['HTTP_COOKIE'] ?? '(none)';
$log = date('Y-m-d H:i:s') . " | {$method} {$path} | Cookie: " . substr($raw_cookie_for_log, 0, 200) . "\n";
file_put_contents(__DIR__ . '/proxy_debug.log', $log, FILE_APPEND);

$ch = curl_init($url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 120);

// Forward cookies
$raw_cookie = $_SERVER['HTTP_COOKIE'] ?? '';
if ($raw_cookie) {
    curl_setopt($ch, CURLOPT_COOKIE, $raw_cookie);
}

// Forward essential headers only
$fwd_headers = ['Host: ' . ($_SERVER['HTTP_HOST'] ?? 'localhost')];
if (!empty($_SERVER['HTTP_ACCEPT'])) {
    $fwd_headers[] = 'Accept: ' . $_SERVER['HTTP_ACCEPT'];
}
if (!empty($_SERVER['HTTP_ACCEPT_LANGUAGE'])) {
    $fwd_headers[] = 'Accept-Language: ' . $_SERVER['HTTP_ACCEPT_LANGUAGE'];
}
if (!empty($_SERVER['HTTP_USER_AGENT'])) {
    $fwd_headers[] = 'User-Agent: ' . $_SERVER['HTTP_USER_AGENT'];
}

// Forward request body for POST/PUT/PATCH
if (in_array($method, ['POST', 'PUT', 'PATCH'])) {
    $body = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    $ct = $_SERVER['CONTENT_TYPE'] ?? 'application/x-www-form-urlencoded';
    $fwd_headers[] = "Content-Type: $ct";
}

curl_setopt($ch, CURLOPT_HTTPHEADER, $fwd_headers);

$response = curl_exec($ch);

if ($response === false) {
    http_response_code(502);
    echo 'Proxy Error: ' . curl_error($ch);
    curl_close($ch);
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$status_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$response_headers = substr($response, 0, $header_size);
$response_body = substr($response, $header_size);

http_response_code($status_code);

// Forward response headers
$skip = ['transfer-encoding', 'connection', 'keep-alive', 'server'];
foreach (explode("\r\n", $response_headers) as $line) {
    $trimmed = trim($line);
    if (empty($trimmed) || strpos($trimmed, 'HTTP/') === 0) continue;
    $hname = strtolower(explode(':', $trimmed)[0] ?? '');
    if (in_array($hname, $skip)) continue;
    header($trimmed, false);
}

echo $response_body;
