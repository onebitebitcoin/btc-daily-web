import { BrowserRouter, Route, Routes } from 'react-router-dom';
import CalendarPage from './CalendarPage';
import EditionPage, { LatestFeed, StatusScreen } from './EditionPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* `/`는 리다이렉트하지 않는다 — 여기서 북마크해야 "항상 최신"이 된다. */}
        <Route path="/" element={<LatestFeed />} />
        <Route path="/d/:date" element={<EditionPage />} />
        {/* 쇼츠 피드는 카드 하나가 공유 단위다 — 딥링크로 그 카드에서 시작한다. */}
        <Route path="/d/:date/:index" element={<EditionPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="*" element={<StatusScreen>존재하지 않는 페이지입니다.</StatusScreen>} />
      </Routes>
    </BrowserRouter>
  );
}
