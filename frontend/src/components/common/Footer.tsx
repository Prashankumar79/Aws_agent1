/**
 * Footer — app footer with branding, copyright, and nav links.
 *
 * PURPOSE:
 *   Persistent footer shown on all pages. Contains copyright notice
 *   and placeholder links for Privacy, Terms, and Docs.
 *
 * CONNECTIONS:
 *   • App.tsx → renders Footer below the main page content
 */

// 🟢 BEGINNER: A functional component that renders the bottom footer bar on every page.
export const Footer = () => {
  const linkStyle = {
    fontSize: '12.5px',
    color: '#6b6b6b',
    textDecoration: 'none' as const,
    transition: 'color 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  };

  return (
    // 🟢 BEGINNER: The <footer> HTML tag. maxWidth + margin auto centers the content on wide screens.
    <footer style={{
      backgroundColor: '#EEEDFE',
      borderTop: '2px solid #5B4EE8',
      padding: '14px 24px',
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {/* 🟢 BEGINNER: Left side — branding and copyright text. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12.5px', color: '#534AB7' }}>
            <i className="ti ti-rocket" style={{ fontSize: '14px' }} />
            <span>© 2026 MigrationPilot from HclTech. All rights reserved.</span>
          </div>
          {/* 🟢 BEGINNER: Right side — navigation links. onMouseEnter/Leave change the text color on hover. */}
          <div style={{ display: 'flex', gap: '20px' }}>
            <a href="#" style={linkStyle}
               onMouseEnter={(e) => e.currentTarget.style.color = '#5B4EE8'}
               onMouseLeave={(e) => e.currentTarget.style.color = '#6b6b6b'}>
              <i className="ti ti-lock" style={{ fontSize: '13px' }} />
              Privacy
            </a>
            <a href="#" style={linkStyle}
               onMouseEnter={(e) => e.currentTarget.style.color = '#5B4EE8'}
               onMouseLeave={(e) => e.currentTarget.style.color = '#6b6b6b'}>
              <i className="ti ti-file-text" style={{ fontSize: '13px' }} />
              Terms
            </a>
            <a href="#" style={linkStyle}
               onMouseEnter={(e) => e.currentTarget.style.color = '#5B4EE8'}
               onMouseLeave={(e) => e.currentTarget.style.color = '#6b6b6b'}>
              <i className="ti ti-book" style={{ fontSize: '13px' }} />
              Docs
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};
