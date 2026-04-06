// life-router.js
// Инструмент для ИИ, который помогает прокладывать маршрут к лучшей жизни

import { VaritypeKB } from './varitype-knowledge-base.json' assert { type: 'json' };

class LifeRouter {
  constructor(userProfile, geographicContext) {
    this.userProfile = userProfile;     // { СБ: 4, ТФ: 5, УБ: 3, ЧВ: 6 }
    this.geoContext = geographicContext; // { city, district, timeOfYear, timeOfDay }
    this.kb = VaritypeKB;
  }
  
  // Определить доминантную масть
  getDominant() {
    return Object.entries(this.userProfile)
      .sort((a, b) => b[1] - a[1])[0][0];
  }
  
  // Получить психологический профиль
  getPsychologicalProfile() {
    const dominant = this.getDominant();
    const level = this.userProfile[dominant];
    
    const vectorData = this.kb.vectors[dominant];
    const levelData = vectorData.levels[level];
    
    return {
      name: vectorData.name,
      essence: vectorData.essence,
      level_name: levelData.name,
      level_description: levelData.name,
      what_they_need: levelData.what_they_need,
      how_to_lead: levelData.how_to_lead,
      route: levelData.route_to_better_life
    };
  }
  
  // Получить рекомендацию по маршруту до работы/дома
  getCommuteRecommendation() {
    const dominant = this.getDominant();
    const level = this.userProfile[dominant];
    const geo = this.geoContext;
    
    // Базовая логика пробок
    const isPeakHour = (geo.timeOfDay >= '07:30' && geo.timeOfDay <= '10:00') ||
                       (geo.timeOfDay >= '17:00' && geo.timeOfDay <= '19:30');
    
    const isMonday = geo.dayOfWeek === 'monday';
    const isFriday = geo.dayOfWeek === 'friday';
    const isWinter = geo.timeOfYear === 'winter';
    
    let advice = {
      optimal_departure: '07:30',
      expected_duration: 30,
      alternative_route: null
    };
    
    if (isPeakHour) {
      advice.expected_duration = 45;
      advice.optimal_departure = '07:30';
      if (isMonday) advice.expected_duration += 10;
      if (isFriday && geo.timeOfDay >= '17:00') advice.expected_duration += 15;
    }
    
    if (isWinter) {
      advice.expected_duration += 15;
      advice.weather_note = 'Зимой дорога может быть скользкой, выезжайте с запасом.';
    }
    
    // Адаптация под психотип
    const templates = this.kb.part_3_integration.route_planning_template;
    const message = templates[`for_${dominant}`] || templates.for_ТФ;
    
    return {
      message: message
        .replace('{time}', geo.timeOfDay)
        .replace('{duration}', advice.expected_duration)
        .replace('{optimal_time}', advice.optimal_departure)
        .replace('{optimal_duration}', advice.expected_duration - 15),
      details: advice
    };
  }
  
  // Получить полный маршрут к лучшей жизни
  getLifeRoute() {
    const profile = this.getPsychologicalProfile();
    const route = profile.route;
    
    // Преобразуем стадии в читаемый план
    const stages = [];
    for (const [stage, action] of Object.entries(route)) {
      if (stage !== 'milestone') {
        stages.push({
          step: stage.replace('stage_', ''),
          action: action,
          status: 'pending'
        });
      }
    }
    
    return {
      current_level: profile.level_name,
      destination: profile.route.milestone,
      stages: stages,
      how_to_lead: profile.how_to_lead,
      estimated_time: this.estimateTimeToMilestone(stages.length)
    };
  }
  
  estimateTimeToMilestone(stageCount) {
    // Минимальные оценки для разных уровней
    const estimates = {
      1: '1-2 недели',
      2: '2-4 недели',
      3: '1-2 месяца',
      4: '2-3 месяца',
      5: '3-6 месяцев',
      6: '6-12 месяцев'
    };
    const dominantLevel = this.userProfile[this.getDominant()];
    return estimates[dominantLevel] || '3-6 месяцев';
  }
  
  // Получить следующий шаг (пошаговое ведение)
  getNextStep() {
    const profile = this.getPsychologicalProfile();
    const route = profile.route;
    
    // Находим первую невыполненную стадию
    for (const [stage, action] of Object.entries(route)) {
      if (stage !== 'milestone' && !this.isStageCompleted(stage)) {
        return {
          current_stage: stage,
          action: action,
          success_criteria: route.milestone,
          encouragement: this.getEncouragement(profile.level_name)
        };
      }
    }
    
    return {
      completed: true,
      message: `Поздравляю! Вы достигли ${profile.route.milestone}. Это большой шаг!`
    };
  }
  
  isStageCompleted(stage) {
    // В реальности это проверяется по данным пользователя
    // Пока заглушка
    return false;
  }
  
  getEncouragement(levelName) {
    const encouragements = {
      'Шестёрка': 'Ты уже сделал первый шаг — это самое трудное. Продолжай!',
      'Семёрка': 'Ты уже лучше, чем вчера. Ещё немного — и ты почувствуешь разницу.',
      'Восьмёрка': 'Ты на правильном пути. Этот шаг приблизит тебя к цели.',
      'Девятка': 'Ты уже сильнее, чем думаешь. Этот шаг будет легче, чем кажется.',
      'Десятка': 'Ты уже профессионал. Этот шаг — естественное продолжение твоего пути.',
      'Мастер': 'Ты уже мастер. Теперь твоя задача — передать знание другим.'
    };
    return encouragements[levelName] || 'Ты справишься. Я рядом.';
  }
}

export default LifeRouter;
