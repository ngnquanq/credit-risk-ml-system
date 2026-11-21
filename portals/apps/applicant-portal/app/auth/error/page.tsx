export default function AuthError() {
  return (
    <div className="card stack" style={{ maxWidth: 560 }}>
      <h1 style={{ margin: 0 }}>Không đăng nhập được</h1>
      <p style={{ margin: 0 }}>Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng thử lại.</p>
      <a className="btn btn-primary" href="/auth/login">Đăng nhập lại</a>
    </div>
  );
}
