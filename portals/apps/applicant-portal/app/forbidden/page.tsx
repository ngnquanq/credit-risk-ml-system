export default function Forbidden() {
  return (
    <div className="card stack" style={{ maxWidth: 560 }}>
      <h1 style={{ margin: 0 }}>Không có quyền truy cập</h1>
      <p style={{ margin: 0 }}>Tài khoản của bạn không được phép xem trang này.</p>
      <a className="btn" href="/">Về trang chủ</a>
    </div>
  );
}
