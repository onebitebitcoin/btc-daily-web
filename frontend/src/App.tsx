import { BrowserRouter, Route, Routes } from 'react-router-dom';
import CalendarPage from './CalendarPage';
import EditionPage, { RootRedirect, StatusScreen } from './EditionPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/d/:date" element={<EditionPage />} />
        {/* 쇼츠 피드는 카드 하나가 공유 단위다 — 딥링크로 그 카드에서 시작한다. */}
        <Route path="/d/:date/:index" element={<EditionPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="*" element={<StatusScreen>존재하지 않는 페이지입니다.</StatusScreen>} />
      </Routes>
    </BrowserRouter>
  );
}
