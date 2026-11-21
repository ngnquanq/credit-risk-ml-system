export default function AuthError() {
  return (
    <div className="card stack" style={{ maxWidth: 560 }}>
      <h1 style={{ margin: 0 }}>Sign-in failed</h1>
      <p style={{ margin: 0 }}>The sign-in expired or was not valid. Please try again.</p>
      <a className="btn btn-primary" href="/auth/login">Sign in</a>
    </div>
  );
}
